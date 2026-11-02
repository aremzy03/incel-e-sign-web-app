"""
Resolve envelope signing_order entries by signer_id and/or email.

Find existing CustomUser by email; if missing, create with an unusable
password and send an invite (same product pattern as contacts invite +
integration JIT users). Always persists signing_order as UUID signer_ids.
"""

from __future__ import annotations

import logging
import re
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)
User = get_user_model()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignerResolutionError(Exception):
    """Raised when a signing_order entry cannot be resolved to a user."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_email(email: str) -> str:
    """Strip and lowercase an email for lookup and storage."""
    return (email or "").strip().lower()


def _looks_like_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value))


def _resolve_full_name(email: str, full_name: str | None) -> str:
    if full_name and str(full_name).strip():
        return str(full_name).strip()
    local_part = email.split("@", 1)[0].strip()
    return local_part or email


def _find_user_by_id(signer_id) -> object | None:
    try:
        uid = uuid.UUID(str(signer_id))
    except (ValueError, TypeError):
        return None
    return User.objects.filter(id=uid).first()


def _find_user_by_email(email: str) -> object | None:
    return User.objects.filter(email__iexact=email).first()


def _ensure_contact(*, owner, email: str, user, name: str) -> None:
    """
    Upsert a Contact for the inviter so invited signers appear in the UI.

    Best-effort: contact failures must not block envelope create.
    """
    try:
        from contacts.models import Contact

        contact, created = Contact.objects.get_or_create(
            owner=owner,
            email=email,
            defaults={
                "name": name or (user.full_name if user else ""),
                "contact_user": user,
            },
        )
        if not created:
            updated = False
            if user and contact.contact_user_id != user.id:
                contact.contact_user = user
                updated = True
            if name and contact.name != name:
                contact.name = name
                updated = True
            if updated:
                contact.save()
    except Exception:
        logger.exception(
            "Failed to upsert contact for invited signer email=%s owner_id=%s",
            email,
            getattr(owner, "id", None),
        )


def _create_invited_user(*, email: str, full_name: str | None, inviter) -> object:
    """
    Create a CustomUser with unusable password and send invite email.

    Mirrors integration JIT create + contacts invite email helpers.
    """
    created_name = _resolve_full_name(email, full_name)
    with transaction.atomic():
        user = User(
            email=email,
            username=email,
            full_name=created_name,
            is_active=True,
        )
        user.set_unusable_password()
        try:
            user.save()
        except IntegrityError:
            # Race: another request created the same email.
            existing = _find_user_by_email(email)
            if existing is None:
                raise
            return existing

    if inviter is not None:
        _ensure_contact(owner=inviter, email=email, user=user, name=created_name)
        try:
            from notifications.utils import send_invite_email

            send_invite_email(email, inviter)
        except Exception:
            # Invite email is best-effort; envelope create must still succeed.
            logger.exception(
                "Failed to send invite email for signer user_id=%s",
                user.id,
            )

    logger.info(
        "Created invited signer user_id=%s email=%s inviter_id=%s",
        user.id,
        email,
        getattr(inviter, "id", None),
    )
    return user


def resolve_signer_entry(entry: dict, *, inviter) -> dict:
    """
    Resolve one signing_order dict to ``{"signer_id": "<uuid>", "order": N}``.

    Accepted shapes (backward compatible):
    - ``{"signer_id": "<uuid>", "order": 1}``
    - ``{"email": "a@b.com", "order": 1}``
    - ``{"signer_id": "<uuid>", "email": "a@b.com", "order": 1}``
      (both must refer to the same user when both resolve)
    - Optional ``full_name`` / ``name`` used only when creating an invited user.

    Args:
        entry: Raw signing_order entry from the client.
        inviter: Envelope creator; used as invite sender and contact owner.

    Returns:
        dict: Normalized entry with string ``signer_id`` and int ``order``.

    Raises:
        SignerResolutionError: Invalid input or inactive user.
    """
    if not isinstance(entry, dict):
        raise SignerResolutionError("Each signing_order entry must be a dictionary.")

    if "order" not in entry:
        raise SignerResolutionError('Each entry must include an "order" key.')

    order = entry["order"]
    if not isinstance(order, int) or order < 1:
        raise SignerResolutionError("order must be a positive integer.")

    raw_signer_id = entry.get("signer_id")
    raw_email = entry.get("email")
    full_name = entry.get("full_name") or entry.get("name")

    has_signer_id = raw_signer_id is not None and str(raw_signer_id).strip() != ""
    has_email = raw_email is not None and str(raw_email).strip() != ""

    if not has_signer_id and not has_email:
        raise SignerResolutionError(
            'Each entry must include "signer_id" and/or "email".'
        )

    user_by_id = None
    if has_signer_id:
        user_by_id = _find_user_by_id(raw_signer_id)
        if user_by_id is None:
            # Allow mistaking an email placed in signer_id (tolerant partner UX).
            sid_text = str(raw_signer_id).strip()
            if _looks_like_email(sid_text):
                has_email = True
                raw_email = sid_text
                has_signer_id = False
                user_by_id = None
            else:
                raise SignerResolutionError(
                    f"Users not found: {[str(raw_signer_id)]}"
                )

    email = normalize_email(str(raw_email)) if has_email else None
    if email is not None and not _looks_like_email(email):
        raise SignerResolutionError(f"Invalid email: {raw_email}")

    user_by_email = _find_user_by_email(email) if email else None

    if user_by_id is not None and user_by_email is not None:
        if user_by_id.id != user_by_email.id:
            raise SignerResolutionError(
                "signer_id and email refer to different users."
            )
        user = user_by_id
    elif user_by_id is not None:
        user = user_by_id
    elif user_by_email is not None:
        user = user_by_email
    else:
        # Unknown email → find-or-invite create path.
        user = _create_invited_user(
            email=email,
            full_name=full_name,
            inviter=inviter,
        )

    if not user.is_active:
        raise SignerResolutionError(
            f"Signer account is inactive: {user.email}"
        )

    return {"signer_id": str(user.id), "order": order}


def resolve_signing_order(signing_order: list, *, inviter) -> list:
    """
    Resolve an entire signing_order list to UUID-based entries.

    Also enforces unique signer_ids, unique sequential orders starting at 1.
    """
    if not isinstance(signing_order, list):
        raise SignerResolutionError("Signing order must be a list.")

    if not signing_order:
        return []

    resolved = []
    signer_ids = set()
    orders = []

    for i, entry in enumerate(signing_order):
        try:
            normalized = resolve_signer_entry(entry, inviter=inviter)
        except SignerResolutionError as exc:
            raise SignerResolutionError(f"Entry {i}: {exc.message}") from exc

        signer_id = normalized["signer_id"]
        order = normalized["order"]

        if signer_id in signer_ids:
            raise SignerResolutionError(f"Duplicate signer_id found: {signer_id}")
        signer_ids.add(signer_id)

        if order in orders:
            raise SignerResolutionError(f"Duplicate order found: {order}")
        orders.append(order)
        resolved.append(normalized)

    orders.sort()
    expected = list(range(1, len(orders) + 1))
    if orders != expected:
        raise SignerResolutionError("Orders must start from 1 and have no gaps.")

    return resolved
