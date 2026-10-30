"""
Service for generating, validating, and managing envelope SigningTokens.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple
from django.utils import timezone
from django.contrib.auth import get_user_model

from envelopes.models import Envelope, SigningToken

logger = logging.getLogger(__name__)
User = get_user_model()


def get_or_create_signing_token(
    envelope: Envelope,
    recipient_email: str,
    recipient_user=None,
    validity_days: int = 7,
) -> SigningToken:
    """
    Retrieve an existing valid signing token or generate a fresh one for the recipient.
    """
    normalized_email = (recipient_email or "").strip().lower()

    if recipient_user is None and normalized_email:
        recipient_user = User.objects.filter(email__iexact=normalized_email).first()

    # Look for an active, unexpired, unused token
    existing = (
        SigningToken.objects.filter(
            envelope=envelope,
            recipient_email__iexact=normalized_email,
            is_revoked=False,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )

    if existing:
        if recipient_user and not existing.recipient_user:
            existing.recipient_user = recipient_user
            existing.save(update_fields=["recipient_user"])
        return existing

    # Create a fresh token
    expires_at = timezone.now() + timezone.timedelta(days=validity_days)
    new_token = SigningToken.objects.create(
        envelope=envelope,
        recipient_email=normalized_email,
        recipient_user=recipient_user,
        expires_at=expires_at,
    )
    logger.info(
        "Created SigningToken %s for envelope %s and recipient %s",
        new_token.id,
        envelope.id,
        normalized_email,
    )
    return new_token


def validate_signing_token(
    token_str: Optional[str],
    envelope_id: Optional[str] = None,
    *,
    allow_used: bool = False,
) -> Tuple[Optional[SigningToken], Optional[str], Optional[str]]:
    """
    Validate a signing token string against database records.

    Args:
        token_str: Raw token string from query params, headers, or body.
        envelope_id: Optional envelope UUID to verify token scope.
        allow_used: When True (for read/status/download views), allow tokens that have
            already been used to sign or belong to completed/rejected envelopes so the
            recipient sees the Completed/Declined status screen rather than an error.

    Returns:
        (signing_token, error_code, error_message)
    """
    if not token_str or not token_str.strip():
        return None, "MISSING_TOKEN", "Signing token is required."

    try:
        signing_token = (
            SigningToken.objects.select_related("envelope", "recipient_user")
            .filter(token=token_str.strip())
            .first()
        )
    except Exception as exc:
        logger.exception("Error querying signing token: %s", exc)
        return None, "QUERY_ERROR", "Error validating signing token."

    if not signing_token:
        return None, "INVALID_TOKEN", "This signing link is invalid or does not exist."

    if envelope_id and str(signing_token.envelope_id) != str(envelope_id):
        return None, "ENVELOPE_MISMATCH", "This signing link is not valid for the requested envelope."

    if timezone.now() >= signing_token.expires_at:
        return signing_token, "TOKEN_EXPIRED", "This signing link has expired. Please sign in or contact the sender."

    if allow_used:
        if signing_token.is_revoked and signing_token.envelope.status == "pending":
            return signing_token, "TOKEN_REVOKED", "This signing link has been revoked."
        return signing_token, None, None

    if signing_token.is_revoked:
        return signing_token, "TOKEN_REVOKED", "This signing link has been revoked."

    if signing_token.used_at is not None:
        return signing_token, "TOKEN_ALREADY_USED", "This document has already been signed with this link."

    if signing_token.envelope.status != "pending":
        return (
            signing_token,
            "ENVELOPE_NOT_PENDING",
            f"This envelope is {signing_token.envelope.status} and can no longer be signed.",
        )

    return signing_token, None, None


def mark_token_used(signing_token: SigningToken) -> None:
    """Mark a signing token as used upon successful signing completion."""
    signing_token.used_at = timezone.now()
    signing_token.save(update_fields=["used_at"])


def revoke_envelope_tokens(envelope: Envelope) -> int:
    """Revoke all unused signing tokens for an envelope."""
    return SigningToken.objects.filter(
        envelope=envelope,
        is_revoked=False,
        used_at__isnull=True,
    ).update(is_revoked=True)

