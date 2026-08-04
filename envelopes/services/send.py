"""
Shared envelope send workflow used by EnvelopeSendView and composite APIs.

Keeps audit, notifications, document status, and signature rebuild identical
across call sites so partner and UI flows stay in parity.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from envelopes.models import Envelope
from signatures.services.reset_workflow import (
    SigningWorkflowInProgressError,
    assert_no_inflight_signing_jobs,
    reset_signing_workflow,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class EnvelopeSendError(Exception):
    """Domain error while sending an envelope (maps to HTTP 4xx)."""

    def __init__(self, message: str, *, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def send_envelope(envelope: Envelope, *, user, request=None) -> Envelope:
    """
    Transition an envelope from draft/rejected to pending and notify signers.

    Args:
        envelope: Envelope instance to send.
        user: Authenticated user performing the send (must be creator).
        request: Optional HTTP request for audit enrichment.

    Returns:
        Envelope: Refreshed envelope in pending status.

    Raises:
        EnvelopeSendError: Business-rule failure (permission, status, self-sign).
        SigningWorkflowInProgressError: Async signing job still running.
    """
    assert_no_inflight_signing_jobs(envelope)

    if envelope.creator != user:
        raise EnvelopeSendError(
            "You can only send envelopes you created.",
            status_code=403,
        )

    if envelope.is_self_sign:
        raise EnvelopeSendError(
            "Self-signed envelopes cannot be sent to recipients.",
            status_code=400,
        )

    if envelope.status not in ("draft", "rejected"):
        raise EnvelopeSendError(
            f"Only draft or rejected envelopes can be sent. Current status: {envelope.status}",
            status_code=400,
        )

    if envelope.status == "rejected":
        envelope.status = "draft"
        envelope.save(update_fields=["status", "updated_at"])

    envelope.status = "pending"
    envelope.save(update_fields=["status", "updated_at"])

    # Update status of all documents in this envelope to 'sent'
    for envelope_document in envelope.envelopedocument_set.select_related("document"):
        document = envelope_document.document
        document.status = "sent"
        document.save(update_fields=["status", "updated_at"], skip_validation=True)

    from audit.utils import log_action
    from integrations.services.jwt_claims import enrich_message_with_client_id

    send_message = (
        f"User {user.full_name or user.username} "
        f"sent envelope '{envelope.name}' with "
        f"{envelope.envelopedocument_set.count()} documents."
    )
    log_action(
        user,
        "SEND_ENVELOPE",
        envelope,
        enrich_message_with_client_id(send_message, request),
        request=request,
    )

    reset_signing_workflow(envelope)

    from notifications.tasks import send_envelope_assigned_email_task
    from notifications.utils import create_notification, create_envelope_sent_notification

    if envelope.signing_order:
        first_signer_id = envelope.signing_order[0]["signer_id"]
        try:
            first_signer = User.objects.get(id=first_signer_id)
            message = create_envelope_sent_notification(envelope)
            create_notification(str(first_signer.id), message)
            try:
                recipient_email = getattr(first_signer, "email", None)
                if recipient_email:
                    send_envelope_assigned_email_task.delay(
                        recipient_email,
                        user.full_name or user.username,
                        envelope.name,
                        str(envelope.id),
                    )
            except Exception:
                logger.exception(
                    "Error sending envelope assigned email envelope_id=%s",
                    envelope.id,
                )
        except User.DoesNotExist:
            logger.warning(
                "First signer missing for envelope_id=%s signer_id=%s",
                envelope.id,
                first_signer_id,
            )

    # Record integration origin + fire outbound webhooks when applicable.
    try:
        from integrations.services.envelope_origin import (
            record_envelope_integration_origin,
        )
        from integrations.services.webhooks import dispatch_envelope_event

        record_envelope_integration_origin(envelope, request=request)
        dispatch_envelope_event("envelope.sent", envelope)
    except Exception:
        logger.exception(
            "Webhook/origin side-effects failed after send envelope_id=%s",
            envelope.id,
        )

    envelope.refresh_from_db()
    return envelope


def send_envelope_by_id(envelope_id, *, user, request=None) -> Envelope:
    """
    Load envelope by primary key and run :func:`send_envelope`.
    """
    envelope = get_object_or_404(Envelope, pk=envelope_id)
    return send_envelope(envelope, user=user, request=request)
