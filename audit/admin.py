"""
Admin interface for audit logging - read-only to maintain immutability.
"""

from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for AuditLog entries.
    
    This ensures audit logs remain immutable and cannot be modified
    through the admin interface, maintaining data integrity.
    """
    list_display = ("created_at", "actor", "action", "target_object", "message")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    ordering = ("-created_at",)
    list_filter = ("action", "created_at", "actor")
    search_fields = ("action", "message", "actor__username", "actor__first_name", "actor__last_name")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        """Prevent adding new audit log entries via admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent editing audit log entries via admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting audit log entries via admin."""
        return False