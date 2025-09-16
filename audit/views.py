"""
API views for audit logging - admin-only access.
"""

from rest_framework import generics, permissions, filters
from .models import AuditLog
from .serializers import AuditLogSerializer


class IsAdmin(permissions.IsAdminUser):
    """Permission class for admin-only access."""
    pass


class AuditLogListView(generics.ListAPIView):
    """
    List view for audit logs - admin only.
    
    Provides paginated list of all audit log entries with search and filtering.
    """
    queryset = AuditLog.objects.all().order_by("-created_at")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    search_fields = [
        "action",
        "message",
        "actor__username",
        "actor__first_name",
        "actor__last_name"
    ]
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "action"]


class AuditLogDetailView(generics.RetrieveAPIView):
    """
    Detail view for individual audit log entries - admin only.
    
    Provides detailed view of a specific audit log entry.
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]