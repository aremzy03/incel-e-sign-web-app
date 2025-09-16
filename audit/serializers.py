"""
Serializers for audit logging API endpoints.
"""

from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for AuditLog model with custom field representations.
    """
    actor = serializers.SerializerMethodField()
    target_object = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "action",
            "target_object",
            "message",
            "ip_address",
            "user_agent",
            "created_at"
        )

    def get_actor(self, obj):
        """Return actor's full name or username."""
        if obj.actor:
            return getattr(obj.actor, "get_full_name", lambda: obj.actor.username)()
        return None

    def get_target_object(self, obj):
        """Return string representation of target object."""
        try:
            return str(obj.target_object)
        except Exception:
            return None
