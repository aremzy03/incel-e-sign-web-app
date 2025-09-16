"""
Audit logging models for tracking user actions and system events.
"""

from django.db import models
import uuid
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings


class AuditLog(models.Model):
    """
    Immutable audit log for tracking user actions and system events.
    
    This model records all significant actions performed by users or the system,
    including document uploads, envelope operations, and signature events.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True,
        on_delete=models.SET_NULL, 
        related_name="audit_logs"
    )
    action = models.CharField(max_length=50)  # e.g. "UPLOAD_DOC", "SEND_ENVELOPE"
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    target_object_id = models.UUIDField()
    target_object = GenericForeignKey('target_content_type', 'target_object_id')
    message = models.TextField()
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        actor = self.actor.get_full_name() if self.actor else "System"
        return f"{self.created_at.isoformat()} | {actor} | {self.action}"