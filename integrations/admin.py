"""
Django admin for Integration registration and one-time secret display.

Staff can create integrations (credentials generated automatically),
deactivate them, and rotate secrets. Raw secrets are shown once via
admin messages and are never persisted.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Integration, IntegrationUserLink
from .services.credentials import issue_credentials, rotate_secret_hash


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
