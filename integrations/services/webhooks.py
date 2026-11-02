"""
Outbound webhook dispatch for first-party integrations.

Builds event payloads, signs them with HMAC-SHA256, queues Celery delivery
with retries. Never logs signing secrets.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from django.utils import timezone

from integrations.models import (
    IntegrationEnvelopeOrigin,
    IntegrationWebhookDelivery,
    IntegrationWebhookEndpoint,
)
from integrations.services.webhook_secrets import decrypt_webhook_secret

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = (
    IntegrationWebhookEndpoint.EVENT_ENVELOPE_SENT,
    IntegrationWebhookEndpoint.EVENT_ENVELOPE_COMPLETED,
)


def build_envelope_event_payload(event_type: str, envelope) -> dict[str, Any]:
    """
    Build the JSON body for an envelope lifecycle webhook.

    Args:
        event_type: ``envelope.sent`` or ``envelope.completed``.
        envelope: Envelope instance.

    Returns:
        dict: JSON-serializable payload (no secrets).
    """
    document_ids = [
        str(doc_id)
        for doc_id in envelope.envelopedocument_set.order_by("order").values_list(
            "document_id", flat=True
        )
    ]
    return {
        "event": event_type,
        "occurred_at": timezone.now().isoformat(),
        "data": {
            "envelope_id": str(envelope.id),
            "status": envelope.status,
            "name": envelope.name,
            "creator_id": str(envelope.creator_id),
            "document_ids": document_ids,
            "signing_order": envelope.signing_order or [],
        },
    }


def sign_payload(raw_secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """
    Create an HMAC signature header value for a webhook body.

    Format: ``t=<unix>,v1=<hex>`` where v1 = HMAC-SHA256(secret, ``t.body``).

    Args:
        raw_secret: Decrypted signing secret (caller must not log).
        body: Exact request body bytes.
        timestamp: Optional unix timestamp; defaults to now.

    Returns:
        str: Signature header value.
    """
    ts = int(timestamp if timestamp is not None else time.time())
    signed_payload = f"{ts}.".encode("utf-8") + body
    digest = hmac.new(
        raw_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={digest}"


def resolve_integration_for_envelope(envelope):
    """
    Return the Integration linked via IntegrationEnvelopeOrigin, or None.
    """
    origin = (
        IntegrationEnvelopeOrigin.objects.select_related("integration")
        .filter(envelope_id=envelope.id)
        .first()
    )
    if origin is None:
        return None
    return origin.integration


def dispatch_envelope_event(event_type: str, envelope) -> list[IntegrationWebhookDelivery]:
    """
    Queue webhook deliveries for all matching active endpoints.

    Args:
        event_type: One of SUPPORTED_EVENTS.
        envelope: Envelope that transitioned.

    Returns:
        list: Created IntegrationWebhookDelivery rows (may be empty).
    """
    if event_type not in SUPPORTED_EVENTS:
        logger.warning("Unsupported webhook event_type=%s", event_type)
        return []

    integration = resolve_integration_for_envelope(envelope)
    if integration is None or not integration.is_active:
        return []

    endpoints = [
        ep
        for ep in integration.webhook_endpoints.filter(is_active=True)
        if ep.listens_for(event_type)
    ]
    if not endpoints:
        return []

    payload = build_envelope_event_payload(event_type, envelope)
    deliveries: list[IntegrationWebhookDelivery] = []

    from integrations.tasks import deliver_webhook_task

    for endpoint in endpoints:
        delivery = IntegrationWebhookDelivery.objects.create(
            endpoint=endpoint,
            event_type=event_type,
            envelope_id=envelope.id,
            payload=payload,
            status=IntegrationWebhookDelivery.STATUS_PENDING,
        )
        deliveries.append(delivery)
        try:
            deliver_webhook_task.delay(str(delivery.id))
        except Exception:
            logger.exception(
                "Failed to enqueue webhook delivery_id=%s",
                delivery.id,
            )
            delivery.status = IntegrationWebhookDelivery.STATUS_FAILED
            delivery.last_error = "Failed to enqueue delivery task"
            delivery.save(update_fields=["status", "last_error", "updated_at"])

    return deliveries


def deliver_webhook_once(delivery_id: str) -> bool:
    """
    Perform a single HTTP POST for a delivery row.

    Returns:
        bool: True when the partner responded with 2xx.
    """
    import urllib.error
    import urllib.request

    delivery = IntegrationWebhookDelivery.objects.select_related(
        "endpoint"
    ).get(pk=delivery_id)
    endpoint = delivery.endpoint

    body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    try:
        raw_secret = decrypt_webhook_secret(endpoint.signing_secret_encrypted)
    except Exception:
        logger.exception(
            "Cannot decrypt webhook secret for endpoint_id=%s",
            endpoint.id,
        )
        delivery.status = IntegrationWebhookDelivery.STATUS_FAILED
        delivery.last_error = "Invalid stored signing secret"
        delivery.attempt_count += 1
        delivery.save(
            update_fields=["status", "last_error", "attempt_count", "updated_at"]
        )
        return False

    signature = sign_payload(raw_secret, body)
    # Intentionally drop reference; never log raw_secret or signature with secret.
    del raw_secret

    request = urllib.request.Request(
        endpoint.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "incel-esign-webhooks/1.0",
            "X-ESign-Event": delivery.event_type,
            "X-ESign-Delivery-Id": str(delivery.id),
            "X-ESign-Signature": signature,
        },
    )

    delivery.attempt_count += 1
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status_code = getattr(response, "status", None) or response.getcode()
            excerpt = response.read(512).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        try:
            excerpt = exc.read(512).decode("utf-8", errors="replace")
        except Exception:
            excerpt = ""
        delivery.response_status_code = status_code
        delivery.response_body_excerpt = excerpt[:512]
        delivery.last_error = f"HTTP {status_code}"
        delivery.status = IntegrationWebhookDelivery.STATUS_FAILED
        delivery.save(
            update_fields=[
                "attempt_count",
                "response_status_code",
                "response_body_excerpt",
                "last_error",
                "status",
                "updated_at",
            ]
        )
        raise
    except Exception as exc:
        delivery.last_error = str(exc)[:512]
        delivery.status = IntegrationWebhookDelivery.STATUS_FAILED
        delivery.save(
            update_fields=["attempt_count", "last_error", "status", "updated_at"]
        )
        raise

    delivery.response_status_code = status_code
    delivery.response_body_excerpt = excerpt[:512]
    if 200 <= int(status_code) < 300:
        delivery.status = IntegrationWebhookDelivery.STATUS_SUCCESS
        delivery.delivered_at = timezone.now()
        delivery.last_error = ""
        delivery.save(
            update_fields=[
                "attempt_count",
                "response_status_code",
                "response_body_excerpt",
                "status",
                "delivered_at",
                "last_error",
                "updated_at",
            ]
        )
        return True

    delivery.status = IntegrationWebhookDelivery.STATUS_FAILED
    delivery.last_error = f"HTTP {status_code}"
    delivery.save(
        update_fields=[
            "attempt_count",
            "response_status_code",
            "response_body_excerpt",
            "status",
            "last_error",
            "updated_at",
        ]
    )
    raise RuntimeError(f"Webhook delivery returned HTTP {status_code}")
