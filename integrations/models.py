"""
Models for first-party server-to-server integrations.

Stores admin-registered partner apps with hashed client credentials,
optional IP allowlists, and stable partner-user link rows.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Integration(models.Model):
    """
    Admin-registered first-party integration with hashed client credentials.

    Partners authenticate with client_id + client_secret for token exchange
    only. The raw secret is never stored; only client_secret_hash is persisted.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the integration.",
    )
    name = models.CharField(
        max_length=255,
        help_text='Human label, e.g. "HR Portal".',
    )
    client_id = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Public opaque identifier for this integration.",
    )
    client_secret_hash = models.CharField(
        max_length=128,
        editable=False,
        help_text="Django password hash of the client secret. Never store the raw secret.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-disable without deleting the integration.",
    )
    allow_jit_user_create = models.BooleanField(
        default=True,
        help_text="When True, token exchange may create users that do not yet exist.",
    )
    allowed_cidrs = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Optional IP allowlist for token exchange. JSON list of IPs or CIDRs, "
            'e.g. ["203.0.113.0/24", "198.51.100.10"]. Empty list = allow all.'
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_integrations",
        help_text="Staff user who registered this integration.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal ops notes.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Integration"
        verbose_name_plural = "Integrations"

    def __str__(self) -> str:
        return f"{self.name} ({self.client_id})"


class IntegrationUserLink(models.Model):
    """
    Maps a partner external_user_id to an e-sign CustomUser for one integration.

    Lets partners keep a stable user key even if the email later changes.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this link row.",
    )
    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="user_links",
        help_text="Integration that owns this partner-user mapping.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="integration_links",
        help_text="Resolved e-sign user for this partner identity.",
    )
    external_user_id = models.CharField(
        max_length=255,
        help_text="Partner application's stable user identifier.",
    )
    linked_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        help_text="When this link was first created.",
    )

    class Meta:
        ordering = ["-linked_at"]
        verbose_name = "Integration user link"
        verbose_name_plural = "Integration user links"
        constraints = [
            models.UniqueConstraint(
                fields=["integration", "external_user_id"],
                name="uniq_integration_external_user_id",
            ),
            models.UniqueConstraint(
                fields=["integration", "user"],
                name="uniq_integration_user",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.integration.client_id}:{self.external_user_id}"
            f"→{self.user_id}"
        )


class IntegrationEnvelopeOrigin(models.Model):
    """
    Links an envelope to the integration JWT that created/sent it.

    Used so outbound webhooks can fire for ``envelope.completed`` even when
    the final signature uses a normal UI token without ``client_id``.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    envelope = models.OneToOneField(
        "envelopes.Envelope",
        on_delete=models.CASCADE,
        related_name="integration_origin",
        help_text="Envelope created or sent via an integration JWT.",
    )
    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="envelope_origins",
        help_text="Integration that originated this envelope.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Integration envelope origin"
        verbose_name_plural = "Integration envelope origins"

    def __str__(self) -> str:
        return f"{self.integration.client_id}→envelope:{self.envelope_id}"


class IntegrationWebhookEndpoint(models.Model):
    """
    Outbound webhook URL registered for an integration.

    Signing secret is stored encrypted (recoverable for HMAC). Raw secrets are
    never logged; admin shows them once on create/rotate.
    """

    EVENT_ENVELOPE_SENT = "envelope.sent"
    EVENT_ENVELOPE_COMPLETED = "envelope.completed"
    EVENT_CHOICES = (
        (EVENT_ENVELOPE_SENT, "Envelope sent"),
        (EVENT_ENVELOPE_COMPLETED, "Envelope completed"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
        help_text="Integration that owns this webhook endpoint.",
    )
    url = models.URLField(
        max_length=2048,
        help_text="HTTPS URL that receives signed POST payloads.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional ops label for this endpoint.",
    )
    signing_secret_encrypted = models.TextField(
        editable=False,
        help_text="Encrypted signing secret used for HMAC. Never log decoded value.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-disable without deleting delivery history.",
    )
    enabled_events = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Event types to deliver, e.g. ["envelope.sent", "envelope.completed"]. '
            "Empty list means all supported events."
        ),
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Integration webhook endpoint"
        verbose_name_plural = "Integration webhook endpoints"

    def __str__(self) -> str:
        return f"{self.integration.client_id} → {self.url}"

    def listens_for(self, event_type: str) -> bool:
        """Return True when this endpoint should receive ``event_type``."""
        if not self.is_active:
            return False
        if not self.enabled_events:
            return True
        return event_type in self.enabled_events


class IntegrationWebhookDelivery(models.Model):
    """
    Delivery attempt log for an outbound webhook (no secrets stored).
    """

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    endpoint = models.ForeignKey(
        IntegrationWebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_type = models.CharField(max_length=64)
    envelope_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Related envelope id when applicable.",
    )
    payload = models.JSONField(
        help_text="JSON body that was (or will be) POSTed. No secrets.",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    response_status_code = models.PositiveIntegerField(null=True, blank=True)
    response_body_excerpt = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Truncated response body for ops; never includes our secrets.",
    )
    last_error = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Integration webhook delivery"
        verbose_name_plural = "Integration webhook deliveries"
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["envelope_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} → {self.endpoint_id} ({self.status})"


class IdempotencyRecord(models.Model):
    """
    Persists successful Idempotency-Key responses for create/send/composite.

    Same actor + key + scope returns the stored response without re-running
    side effects. Failures are not stored.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    key = models.CharField(
        max_length=255,
        help_text="Value of the Idempotency-Key request header.",
    )
    scope = models.CharField(
        max_length=128,
        help_text="Logical endpoint scope, e.g. envelopes.create.",
    )
    response_status = models.PositiveIntegerField()
    response_body = models.JSONField(
        help_text="Snapshot of the successful JSON response body.",
    )
    envelope_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Envelope created/sent when applicable.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Idempotency record"
        verbose_name_plural = "Idempotency records"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key", "scope"],
                name="uniq_idempotency_user_key_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["envelope_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key} user={self.user_id}"
