"""
Django admin for Integration registration and one-time secret display.

Staff can create integrations (credentials generated automatically),
deactivate them, and rotate secrets. Raw secrets are shown once via
admin messages and are never persisted in plaintext for client credentials.
Webhook signing secrets are encrypted at rest and shown once on create/rotate.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    IdempotencyRecord,
    Integration,
    IntegrationEnvelopeOrigin,
    IntegrationUserLink,
    IntegrationWebhookDelivery,
    IntegrationWebhookEndpoint,
)
from .services.credentials import (
    generate_client_secret,
    issue_credentials,
    rotate_secret_hash,
)
from .services.webhook_secrets import encrypt_webhook_secret


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    """
    Admin configuration for Integration model.

    On create, generates client_id + secret, stores only the hash, and
    surfaces the raw secret once. Rotate action invalidates the old hash
    and shows the new secret once.
    """

    list_display = (
        "name",
        "client_id",
        "is_active",
        "allow_jit_user_create",
        "created_by",
        "created_at",
    )
    list_filter = ("is_active", "allow_jit_user_create", "created_at")
    search_fields = ("name", "client_id", "notes")
    ordering = ("-created_at",)
    actions = ("deactivate_integrations", "rotate_client_secret")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "is_active",
                    "allow_jit_user_create",
                    "allowed_cidrs",
                    "notes",
                ),
            },
        ),
        (
            "Credentials",
            {
                "fields": ("client_id",),
                "description": (
                    "Client secret is generated automatically and shown once "
                    "after create or rotate. Only the hash is stored."
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("id", "created_by", "created_at", "updated_at"),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """
        client_id is assigned on create; metadata fields are always read-only.
        """
        base = ("id", "created_by", "created_at", "updated_at")
        if obj is None:
            return base
        return base + ("client_id",)

    def get_fieldsets(self, request, obj=None):
        """Hide credentials section on the add form until client_id exists."""
        if obj is None:
            return (
                (
                    None,
                    {
                        "fields": (
                            "name",
                            "is_active",
                            "allow_jit_user_create",
                            "allowed_cidrs",
                            "notes",
                        ),
                        "description": (
                            "Saving will generate a client_id and client_secret. "
                            "The secret is shown once on the next page. "
                            "allowed_cidrs is a JSON list of IPs/CIDRs; empty = allow all."
                        ),
                    },
                ),
            )
        return self.fieldsets

    def save_model(self, request, obj, form, change):
        """
        On create, issue credentials and attach created_by.

        The raw secret is stashed on the request for one-time display in
        response_add — it is never written to the database.
        """
        if not change:
            client_id, raw_secret, secret_hash = issue_credentials()
            obj.client_id = client_id
            obj.client_secret_hash = secret_hash
            if request.user.is_authenticated:
                obj.created_by = request.user
            # Intentionally not logged — one-time admin display only.
            request._integration_raw_secret = raw_secret  # noqa: SLF001
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        """Show the generated client secret once after successful create."""
        raw_secret = getattr(request, "_integration_raw_secret", None)
        if raw_secret:
            messages.warning(
                request,
                format_html(
                    "Integration created. Copy the client secret now — "
                    "it will not be shown again.<br>"
                    "<strong>client_id:</strong> <code>{}</code><br>"
                    "<strong>client_secret:</strong> <code>{}</code>",
                    obj.client_id,
                    raw_secret,
                ),
            )
        return super().response_add(request, obj, post_url_continue)

    @admin.action(description="Deactivate selected integrations")
    def deactivate_integrations(self, request, queryset):
        """Soft-disable integrations by setting is_active=False."""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {updated} integration(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Rotate client secret (shows new secret once)")
    def rotate_client_secret(self, request, queryset):
        """
        Replace the secret hash for exactly one selected integration.

        The new raw secret is shown once via an admin message.
        """
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one integration to rotate its secret.",
                level=messages.ERROR,
            )
            return

        integration = queryset.get()
        raw_secret, secret_hash = rotate_secret_hash()
        integration.client_secret_hash = secret_hash
        integration.save(update_fields=["client_secret_hash", "updated_at"])
        # Intentionally not logged — one-time admin display only.
        messages.warning(
            request,
            format_html(
                "Secret rotated for <strong>{}</strong>. Copy the new client "
                "secret now — it will not be shown again.<br>"
                "<strong>client_id:</strong> <code>{}</code><br>"
                "<strong>client_secret:</strong> <code>{}</code>",
                integration.name,
                integration.client_id,
                raw_secret,
            ),
        )


@admin.register(IntegrationUserLink)
class IntegrationUserLinkAdmin(admin.ModelAdmin):
    """Read-oriented admin for partner-user link rows (created on token exchange)."""

    list_display = (
        "external_user_id",
        "integration",
        "user",
        "linked_at",
    )
    list_filter = ("integration", "linked_at")
    search_fields = (
        "external_user_id",
        "user__email",
        "integration__client_id",
        "integration__name",
    )
    ordering = ("-linked_at",)
    readonly_fields = ("id", "linked_at")
    raw_id_fields = ("user", "integration")


@admin.register(IntegrationWebhookEndpoint)
class IntegrationWebhookEndpointAdmin(admin.ModelAdmin):
    """
    Register partner webhook URLs and manage signing secrets.

    On create/rotate, a high-entropy signing secret is generated, encrypted
    for storage, and shown once. Use HTTPS URLs in production.
    """

    list_display = (
        "integration",
        "url",
        "is_active",
        "enabled_events",
        "created_at",
    )
    list_filter = ("is_active", "integration", "created_at")
    search_fields = ("url", "description", "integration__client_id", "integration__name")
    ordering = ("-created_at",)
    actions = ("deactivate_endpoints", "rotate_signing_secret")
    raw_id_fields = ("integration",)
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "integration",
                    "url",
                    "description",
                    "is_active",
                    "enabled_events",
                ),
                "description": (
                    "enabled_events is a JSON list such as "
                    '["envelope.sent", "envelope.completed"]. '
                    "Empty list = all supported events. Use HTTPS in production."
                ),
            },
        ),
        (
            "Metadata",
            {"fields": ("id", "created_at", "updated_at")},
        ),
    )

    def save_model(self, request, obj, form, change):
        """Issue an encrypted signing secret on create."""
        if not change or not obj.signing_secret_encrypted:
            raw_secret = generate_client_secret()
            obj.signing_secret_encrypted = encrypt_webhook_secret(raw_secret)
            request._webhook_raw_secret = raw_secret  # noqa: SLF001
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        """Show webhook signing secret once after create."""
        raw_secret = getattr(request, "_webhook_raw_secret", None)
        if raw_secret:
            messages.warning(
                request,
                format_html(
                    "Webhook endpoint created. Copy the signing secret now — "
                    "it will not be shown again.<br>"
                    "<strong>url:</strong> <code>{}</code><br>"
                    "<strong>signing_secret:</strong> <code>{}</code>",
                    obj.url,
                    raw_secret,
                ),
            )
        return super().response_add(request, obj, post_url_continue)

    @admin.action(description="Deactivate selected webhook endpoints")
    def deactivate_endpoints(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {updated} webhook endpoint(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Rotate webhook signing secret (shows once)")
    def rotate_signing_secret(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one webhook endpoint to rotate its secret.",
                level=messages.ERROR,
            )
            return
        endpoint = queryset.get()
        raw_secret = generate_client_secret()
        endpoint.signing_secret_encrypted = encrypt_webhook_secret(raw_secret)
        endpoint.save(update_fields=["signing_secret_encrypted", "updated_at"])
        messages.warning(
            request,
            format_html(
                "Signing secret rotated for <strong>{}</strong>. Copy it now — "
                "it will not be shown again.<br>"
                "<strong>signing_secret:</strong> <code>{}</code>",
                endpoint.url,
                raw_secret,
            ),
        )


@admin.register(IntegrationWebhookDelivery)
class IntegrationWebhookDeliveryAdmin(admin.ModelAdmin):
    """Read-only delivery log for ops (no secrets in payload)."""

    list_display = (
        "event_type",
        "endpoint",
        "status",
        "attempt_count",
        "response_status_code",
        "envelope_id",
        "created_at",
    )
    list_filter = ("status", "event_type", "created_at")
    search_fields = ("envelope_id", "endpoint__url", "last_error")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "endpoint",
        "event_type",
        "envelope_id",
        "payload",
        "status",
        "attempt_count",
        "response_status_code",
        "response_body_excerpt",
        "last_error",
        "created_at",
        "updated_at",
        "delivered_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IntegrationEnvelopeOrigin)
class IntegrationEnvelopeOriginAdmin(admin.ModelAdmin):
    """Read-only map of envelopes originated via integration JWTs."""

    list_display = ("envelope", "integration", "created_at")
    list_filter = ("integration", "created_at")
    search_fields = ("envelope__id", "integration__client_id")
    ordering = ("-created_at",)
    readonly_fields = ("id", "envelope", "integration", "created_at")
    raw_id_fields = ("envelope", "integration")

    def has_add_permission(self, request):
        return False


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    """Ops visibility into Idempotency-Key snapshots."""

    list_display = ("scope", "key", "user", "response_status", "envelope_id", "created_at")
    list_filter = ("scope", "response_status", "created_at")
    search_fields = ("key", "user__email", "envelope_id")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "user",
        "key",
        "scope",
        "response_status",
        "response_body",
        "envelope_id",
        "created_at",
    )
    raw_id_fields = ("user",)

    def has_add_permission(self, request):
        return False
