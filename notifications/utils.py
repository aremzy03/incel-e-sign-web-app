"""
Utility functions for notifications in the E-Sign application.
"""

from celery import shared_task
from .models import Notification


def get_user_display_name(user):
    """
    Get the display name for a user (full_name or username).
    
    Args:
        user: User instance
        
    Returns:
        str: Display name for the user
    """
    return user.full_name if user.full_name else user.username


@shared_task
def create_notification(user_id, message):
    """
    Create a notification for a specific user.
    
    Args:
        user_id (str): UUID of the user to notify
        message (str): Notification message content
    
    Returns:
        str: ID of the created notification or None if user not found
    """
    from users.models import CustomUser
    
    try:
        user = CustomUser.objects.get(id=user_id)
        notification = Notification.objects.create(user=user, message=message)
        return str(notification.id)
    except CustomUser.DoesNotExist:
        return None


def create_envelope_sent_notification(envelope):
    """
    Create notification for envelope sent to first signer.
    
    Args:
        envelope: Envelope instance
        
    Returns:
        str: Notification message
    """
    creator_name = get_user_display_name(envelope.creator)
    file_name = envelope.document.file_name
    return f"{creator_name} has requested you to sign the document '{file_name}'."


def create_signer_turn_notification(envelope):
    """
    Create notification for signer's turn.
    
    Args:
        envelope: Envelope instance
        
    Returns:
        str: Notification message
    """
    file_name = envelope.document.file_name
    return f"It is now your turn to sign the document '{file_name}'."


def create_envelope_completed_notification(envelope):
    """
    Create notification for envelope completion.
    
    Args:
        envelope: Envelope instance
        
    Returns:
        str: Notification message
    """
    file_name = envelope.document.file_name
    return f"Your envelope for '{file_name}' has been fully signed and completed."


def create_signer_declined_notification(envelope, signer):
    """
    Create notification for signer declining.
    
    Args:
        envelope: Envelope instance
        signer: User instance who declined
        
    Returns:
        str: Notification message
    """
    signer_name = get_user_display_name(signer)
    file_name = envelope.document.file_name
    return f"Signer {signer_name} declined to sign the document '{file_name}'. The envelope has been rejected."


def create_envelope_rejected_notification(envelope):
    """
    Create notification for envelope rejection by creator.
    
    Args:
        envelope: Envelope instance
        
    Returns:
        str: Notification message
    """
    creator_name = get_user_display_name(envelope.creator)
    file_name = envelope.document.file_name
    return f"{creator_name} has cancelled the envelope for '{file_name}'."
