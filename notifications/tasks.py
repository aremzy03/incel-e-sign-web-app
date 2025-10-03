"""
Celery tasks for the notifications app.
"""

from celery import shared_task
from .models import Notification


@shared_task
def create_notification(user_id: str, message: str) -> str | None:
    """
    Create a notification for a specific user.

    Args:
        user_id (str): UUID of the user to notify
        message (str): Notification message content

    Returns:
        str | None: ID of the created notification or None if user not found
    """
    from users.models import CustomUser

    try:
        user = CustomUser.objects.get(id=user_id)
        notification = Notification.objects.create(user=user, message=message)
        return str(notification.id)
    except CustomUser.DoesNotExist:
        return None


def _build_invite_email_body(inviter_name: str) -> str:
    return (
        f"Hi, {inviter_name} has invited you to sign documents on Incel E-Sign. "
        f"Click here to register."
    )


@shared_task
def send_invite_email_task(email: str, inviter_name: str) -> None:
    try:
        # Reuse Notification model as a stub for in-app trace; integrate actual email later
        from users.models import CustomUser
        system_user = CustomUser.objects.filter(is_superuser=True).first()
        message = _build_invite_email_body(inviter_name)
        if system_user:
            Notification.objects.create(user=system_user, message=f"Invite email queued to {email}: {message}")
    except Exception:
        return None


