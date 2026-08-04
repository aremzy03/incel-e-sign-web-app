"""
Celery tasks for integration webhook delivery with retry/backoff.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    name="integrations.tasks.deliver_webhook_task",
)
def deliver_webhook_task(self, delivery_id: str) -> bool:
    """
    Deliver one webhook payload; Celery retries on failure.

    Args:
        delivery_id: UUID string of IntegrationWebhookDelivery.

    Returns:
        bool: True on HTTP 2xx success.
    """
    from integrations.services.webhooks import deliver_webhook_once

    # Never log secrets; delivery id is safe.
    logger.info(
        "Delivering webhook delivery_id=%s attempt=%s",
        delivery_id,
        self.request.retries + 1,
    )
    return deliver_webhook_once(delivery_id)
