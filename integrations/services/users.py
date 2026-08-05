"""
User resolution helpers for integrations.

Normalizes email, finds an existing CustomUser, or JIT-creates one when
the integration allows it. Never logs secrets or tokens.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class UserInactiveError(Exception):
    """Raised when the resolved user account is inactive."""


class UserNotFoundError(Exception):
    """Raised when no user exists and JIT create is not allowed."""


def normalize_email(email: str) -> str:
    """
    Normalize an email for lookup and storage.

    Args:
        email: Raw email from the partner request.

    Returns:
        str: Stripped, lowercased email address.
    """
    return (email or "").strip().lower()


def _resolve_full_name(email: str, full_name: str | None) -> str:
    """
    Prefer a provided full_name; otherwise fall back to the email local-part.
    """
    if full_name and full_name.strip():
        return full_name.strip()
    local_part = email.split("@", 1)[0].strip()
    return local_part or email


def resolve_user_for_integration(
    *,
    email: str,
    full_name: str | None = None,
    allow_jit_create: bool,
):
    """
    Find or JIT-create a CustomUser for token exchange.

    Args:
        email: Partner-asserted user email (will be normalized).
        full_name: Optional display name. Used on JIT create; fills empty
            full_name on existing users only.
        allow_jit_create: When True, create the user if missing.

    Returns:
        tuple: ``(user, created)`` where ``created`` is True for JIT create.

    Raises:
        UserNotFoundError: User missing and JIT create disabled.
        UserInactiveError: Matching user exists but ``is_active`` is False.
    """
    normalized = normalize_email(email)
    user = User.objects.filter(email__iexact=normalized).first()

    if user is not None:
        if not user.is_active:
            raise UserInactiveError("User account is inactive.")
        # Policy: only fill full_name when the existing value is empty.
        if not (user.full_name or "").strip() and full_name and full_name.strip():
            user.full_name = full_name.strip()
            user.save(update_fields=["full_name", "updated_at"])
        return user, False

    if not allow_jit_create:
        raise UserNotFoundError("User not found.")

    created_name = _resolve_full_name(normalized, full_name)
    user = User(
        email=normalized,
        username=normalized,
        full_name=created_name,
        is_active=True,
    )
    user.set_unusable_password()
    user.save()
    logger.info(
        "JIT created user via integration token exchange user_id=%s",
        user.id,
    )
    return user, True
