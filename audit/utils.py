"""
Audit logging utilities for creating audit log entries.
"""

from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


def log_action(actor, action, target, message, request=None):
    """
    Create an AuditLog entry for tracking user actions and system events.
    
    Args:
        actor: The user performing the action (can be None for system actions)
        action (str): The action being performed (e.g., "UPLOAD_DOC", "SEND_ENVELOPE")
        target: The model instance being acted upon
        message (str): Descriptive message about the action
        request: Optional Django request object to extract IP and user agent
    
    Returns:
        AuditLog: The created audit log entry, or None if creation failed
    """
    try:
        target_ct = ContentType.objects.get_for_model(target.__class__)
        ip = None
        ua = None
        
        if request is not None:
            # Extract IP address from request
            ip = request.META.get("REMOTE_ADDR") or request.META.get("HTTP_X_FORWARDED_FOR")
            # Extract user agent
            ua = request.META.get("HTTP_USER_AGENT")
        
        return AuditLog.objects.create(
            actor=(actor if actor and getattr(actor, "is_authenticated", False) else None),
            action=action,
            target_content_type=target_ct,
            target_object_id=target.id,
            message=message,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception as e:
        # Do not leak exceptions — log to django logger instead
        import logging
        logging.getLogger(__name__).exception("Failed to create audit log: %s", e)
        return None
