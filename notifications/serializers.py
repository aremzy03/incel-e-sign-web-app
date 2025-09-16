"""
Serializers for notifications in the E-Sign application.
"""

from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model.
    
    Fields:
        id: Unique identifier (UUID)
        message: Notification message content
        is_read: Whether the notification has been read
        created_at: Timestamp when notification was created
    """
    
    class Meta:
        model = Notification
        fields = ['id', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']
