"""
Celery tasks for the notifications app.
"""

from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
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


@shared_task
def send_invite_email_task(email: str, inviter_name: str, registration_url: str) -> None:
    subject = "You're invited to Incel E‑Sign"
    context = {
        'email_title': subject,
        'inviter_name': inviter_name,
        'registration_url': f"{settings.FRONTEND_BASE_URL}/register", # Updated URL format
        'brand_name': 'Incel E-Sign',
        'year': '2025',
    }
    html_message = render_to_string('invite_email.html', context)
    email_message = EmailMessage(subject, html_message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [email])
    email_message.content_subtype = "html"
    email_message.send(fail_silently=True)


@shared_task
def send_envelope_assigned_email_task(recipient_email: str, creator_name: str, envelope_name: str, envelope_id: str) -> None:
    subject = "You have a document to sign"
    context = {
        'email_title': subject,
        'user_name': recipient_email, # Assuming recipient_email can be used as user_name for now
        'creator_name': creator_name,
        'document_title': envelope_name,
        'sign_document_url': f"{settings.FRONTEND_BASE_URL}/dashboard/envelopes/{envelope_id}/sign",
        'brand_name': 'Incel E-Sign',
        'year': '2025',
    }
    html_message = render_to_string('envelope_assigned.html', context)
    email_message = EmailMessage(subject, html_message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email])
    email_message.content_subtype = "html"
    email_message.send(fail_silently=True)


@shared_task
def send_turn_to_sign_email_task(recipient_email: str, envelope_name: str, envelope_id: str) -> None:
    subject = "It's your turn to sign"
    context = {
        'email_title': subject,
        'user_name': recipient_email, # Assuming recipient_email can be used as user_name for now
        'document_title': envelope_name,
        'sign_document_url': f"{settings.FRONTEND_BASE_URL}/dashboard/envelopes/{envelope_id}/sign",
        'brand_name': 'Incel E-Sign',
        'year': '2025',
    }
    html_message = render_to_string('turn_to_sign.html', context)
    email_message = EmailMessage(subject, html_message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email])
    email_message.content_subtype = "html"
    email_message.send(fail_silently=True)


@shared_task
def send_email_confirmation_task(recipient_email: str, confirmation_url: str, full_name: str | None = None) -> None:
    subject = "Confirm your email address"
    context = {
        'email_title': subject,
        'user_name': full_name if full_name else recipient_email,
        'verification_url': confirmation_url,
        'brand_name': 'Incel E-Sign',
        'year': '2025',
    }
    html_message = render_to_string('account_verification.html', context)
    email_message = EmailMessage(subject, html_message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient_email])
    email_message.content_subtype = "html"
    email_message.send(fail_silently=True)


