"""
Utility functions for notifications in the E-Sign application.
"""

from .models import Notification
from .tasks import create_notification as create_notification_task, send_invite_email_task


def get_user_display_name(user):
    """
    Get the display name for a user (full_name or username).
    
    Args:
        user: User instance
        
    Returns:
        str: Display name for the user
    """
    return user.full_name if user.full_name else user.username


def create_notification(user_id, message):
    """Proxy to the Celery task for creating a notification."""
    return create_notification_task.delay(user_id, message)


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


def create_signer_declined_notification(envelope, signer, decline_message: str = None):
    """
    Create notification for signer declining.
    
    Args:
        envelope: Envelope instance
        signer: User instance who declined
        decline_message (str, optional): The message or reason for declining. Defaults to None.
        
    Returns:
        str: Notification message
    """
    signer_name = get_user_display_name(signer)
    file_name = envelope.document.file_name
    message = f"Signer {signer_name} declined to sign the document '{file_name}'. The envelope has been rejected."
    if decline_message:
        message += f" Reason: {decline_message}"
    return message


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


def _build_invite_email_body(inviter_name: str) -> str:
    return (
        f"Hi, {inviter_name} has invited you to sign documents on Incel E-Sign. "
        f"Click here to register."
    )


def _send_invite_email_task(email: str, inviter_name: str):
    return send_invite_email_task.delay(email, inviter_name)


def send_invite_email(email: str, inviter):
    """
    Helper to send invite email via Celery.

    Args:
        email (str): Recipient email to invite.
        inviter (User): User sending the invite.
    """
    inviter_name = get_user_display_name(inviter)
    try:
        _send_invite_email_task(email, inviter_name)
    except Exception:
        # Fallback to synchronous path if Celery not running
        send_invite_email_task(email, inviter_name)
