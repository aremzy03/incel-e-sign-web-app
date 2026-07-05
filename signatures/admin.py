"""Django admin registrations for signature models."""

from django.contrib import admin

from signatures.models import SigningJob, Signature, UserSignature


@admin.register(SigningJob)
class SigningJobAdmin(admin.ModelAdmin):
    list_display = ("id", "envelope", "signer", "status", "attempt_count", "created_at", "completed_at")
    list_filter = ("status", "is_self_sign")
    search_fields = ("id", "envelope__id", "signer__email")
    readonly_fields = ("created_at", "updated_at", "completed_at", "celery_task_id")


@admin.register(Signature)
class SignatureAdmin(admin.ModelAdmin):
    list_display = ("id", "envelope", "signer", "status", "signed_at")
    list_filter = ("status",)


@admin.register(UserSignature)
class UserSignatureAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "is_default", "created_at")
