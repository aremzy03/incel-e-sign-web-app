"""
Notification model for the E-Sign application.
"""

from django.db import models
from django.conf import settings
import uuid


class Notification(models.Model):
    """
    Model representing in-app notifications for users.
    
    Fields:
        id: Unique identifier (UUID)
        user: User who receives the notification
        message: Notification message content
        is_read: Whether the notification has been read
        created_at: Timestamp when notification was created
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
    
    def __str__(self):
        return f"Notification for {self.user.email}: {self.message[:50]}..."