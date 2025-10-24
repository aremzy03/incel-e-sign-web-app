"""
Tests for Celery email tasks in notifications.tasks.
"""

import pytest
from unittest.mock import patch


@patch("notifications.tasks.EmailMessage")
def test_send_envelope_assigned_email_task_sends_email(mock_email_message):
    from notifications.tasks import send_envelope_assigned_email_task

    send_envelope_assigned_email_task("user@example.com", "Creator Name", "contract.pdf", "envelope-uuid-123")

    assert mock_email_message.called
    instance = mock_email_message.return_value
    instance.send.assert_called_once()


@patch("notifications.tasks.EmailMessage")
def test_send_turn_to_sign_email_task_sends_email(mock_email_message):
    from notifications.tasks import send_turn_to_sign_email_task

    send_turn_to_sign_email_task("user2@example.com", "nda.pdf", "envelope-uuid-456")

    assert mock_email_message.called
    instance = mock_email_message.return_value
    instance.send.assert_called_once()


@patch("notifications.tasks.EmailMessage")
def test_send_invite_email_task_sends_email(mock_email_message):
    from notifications.tasks import send_invite_email_task

    send_invite_email_task("invitee@example.com", "Inviter Name")

    assert mock_email_message.called
    instance = mock_email_message.return_value
    instance.send.assert_called_once()


@patch("notifications.tasks.EmailMessage")
def test_send_email_confirmation_task_sends_email(mock_email_message):
    from notifications.tasks import send_email_confirmation_task

    send_email_confirmation_task(
        "newuser@example.com",
        "http://localhost:3000/confirm-email?token=abc",
        "New User",
    )

    assert mock_email_message.called
    instance = mock_email_message.return_value
    instance.send.assert_called_once()


