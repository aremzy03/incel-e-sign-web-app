import pytest
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from documents.models import Document
from envelopes.models import Envelope


@pytest.mark.django_db
@patch("notifications.tasks.send_envelope_assigned_email_task.delay")
def test_envelope_send_emails_first_signer(mock_delay, client):
    User = get_user_model()
    creator = User.objects.create_user(
        username="creator@example.com", email="creator@example.com", full_name="Creator", password="StrongPassw0rd!"
    )
    signer = User.objects.create_user(
        username="signer@example.com", email="signer@example.com", full_name="Signer", password="StrongPassw0rd!"
    )
    client.force_login(creator)

    # Minimal document and envelope setup
    doc = Document.objects.create(
        owner=creator, file_url="/media/documents/test.pdf", file_name="test.pdf", file_size=1000, status="draft"
    )
    env = Envelope.objects.create(
        document=doc,
        creator=creator,
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
        status="draft",
    )

    url = reverse("envelopes-send", kwargs={"pk": str(env.id)})
    res = client.post(url)

    assert res.status_code == 200
    assert mock_delay.called

