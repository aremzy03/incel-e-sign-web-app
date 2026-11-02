"""
Record which integration JWT originated an envelope (for webhook routing).
"""

from __future__ import annotations

import logging

from integrations.models import Integration, IntegrationEnvelopeOrigin
from integrations.services.jwt_claims import get_jwt_client_id

logger = logging.getLogger(__name__)


def record_envelope_integration_origin(envelope, *, request=None) -> None:
    """
    Persist IntegrationEnvelopeOrigin when the request carries client_id.

    Idempotent: if an origin already exists, leave it unchanged.

    Args:
        envelope: Envelope that was created or sent.
        request: Optional request with a SimpleJWT access token.
    """
    client_id = get_jwt_client_id(request)
    if not client_id:
        return

    if IntegrationEnvelopeOrigin.objects.filter(envelope=envelope).exists():
        return

    integration = Integration.objects.filter(
        client_id=client_id,
        is_active=True,
    ).first()
    if integration is None:
        logger.warning(
            "No active integration for client_id when recording envelope origin "
            "envelope_id=%s",
            envelope.id,
        )
        return

    IntegrationEnvelopeOrigin.objects.get_or_create(
        envelope=envelope,
        defaults={"integration": integration},
    )
