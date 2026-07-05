"""
Cutover helpers for the async signing architecture migration.
"""

from django.conf import settings


FROZEN_ENVELOPE_MESSAGE = (
    "Envelope frozen for system upgrade. Ask the creator to resend."
)


def is_envelope_frozen(envelope) -> bool:
    """
    Return True when a pre-cutover pending envelope must not be signed.
    """
    cutover = getattr(settings, "SIGNING_CUTOVER_AT", None)
    if cutover is None:
        return False
    if envelope.status != "pending":
        return False
    return envelope.created_at < cutover


def uses_async_signing_pipeline(envelope) -> bool:
    """Return True when envelope should use the v2 async signing pipeline."""
    cutover = getattr(settings, "SIGNING_CUTOVER_AT", None)
    if cutover is None:
        return True
    return envelope.created_at >= cutover
