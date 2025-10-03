import pytest
from unittest.mock import patch
from django.urls import reverse


@patch("notifications.tasks.send_email_confirmation_task.delay")
def test_registration_triggers_confirmation_email(mock_delay, client):
    url = reverse("auth-register")
    payload = {
        "email": "reg@example.com",
        "full_name": "Reg User",
        "password": "StrongPassw0rd!",
    }
    res = client.post(url, payload, content_type="application/json")

    assert res.status_code == 201
    assert mock_delay.called
    args, kwargs = mock_delay.call_args
    # Ensure email and confirmation link present
    assert args[0] == "reg@example.com"
    assert "confirm-email" in args[1]

