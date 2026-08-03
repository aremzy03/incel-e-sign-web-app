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
