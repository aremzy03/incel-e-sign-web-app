"""
Dashboard helpers for envelope views.
"""

from envelopes.models import Envelope
from envelopes.serializers import _get_envelope_current_signer


def get_envelopes_where_user_is_current_signer(user):
    """
    Return pending, non-self-sign envelopes where the user is the current signer.

    The current signer is the pending signature with the lowest signing order.
    """
    pending_envelopes = (
        Envelope.objects
        .filter(
            status='pending',
            is_self_sign=False,
            signatures__signer=user,
            signatures__status='pending',
        )
        .distinct()
        .select_related('creator')
        .prefetch_related('signatures__signer')
        .order_by('-updated_at')
    )
    return [
        envelope for envelope in pending_envelopes
        if (current := _get_envelope_current_signer(envelope))
        and current['id'] == str(user.id)
    ]
