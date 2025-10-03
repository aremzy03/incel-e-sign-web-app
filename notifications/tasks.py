"""
Celery tasks for the notifications app.
"""

from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
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
    subject = "You're invited to Incel E‑Sign"
    body = _build_invite_email_body(inviter_name)
    EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [email]).send(fail_silently=True)


@shared_task
def send_envelope_assigned_email_task(recipient_email: str, creator_name: str, file_name: str) -> None:
    subject = "You have a document to sign"
    body = (
        f"Hi,\n\n{creator_name} has requested you to sign the document '{file_name}'.\n"
        f"Please sign when convenient.\n\n"
        f"Thanks,\nIncel E‑Sign"
    )
    EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email]).send(fail_silently=True)


@shared_task
def send_turn_to_sign_email_task(recipient_email: str, file_name: str) -> None:
    subject = "It's your turn to sign"
    body = (
        f"Hi,\n\nIt is now your turn to sign the document '{file_name}'.\n"
        f"Please proceed to sign to keep the process moving.\n\n"
        f"Thanks,\nIncel E‑Sign"
    )
    EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email]).send(fail_silently=True)


@shared_task
def send_email_confirmation_task(recipient_email: str, confirmation_url: str, full_name: str | None = None) -> None:
    subject = "Confirm your email address"
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Welcome to Incel E‑Sign! Please confirm your email address by clicking the link below:\n"
        f"{confirmation_url}\n\n"
        f"If you didn't sign up, you can ignore this email.\n\n"
        f"Thanks,\nIncel E‑Sign"
    )
    EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email]).send(fail_silently=True)


