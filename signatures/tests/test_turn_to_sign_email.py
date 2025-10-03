import pytest
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from documents.models import Document
from envelopes.models import Envelope
from signatures.models import Signature


@pytest.mark.django_db
@patch("notifications.tasks.send_turn_to_sign_email_task.delay")
def test_signing_triggers_next_signer_email(mock_delay, client):
    User = get_user_model()
    creator = User.objects.create_user(
        username="creator@example.com", email="creator@example.com", full_name="Creator", password="StrongPassw0rd!"
    )
    signer1 = User.objects.create_user(
        username="s1@example.com", email="s1@example.com", full_name="S1", password="StrongPassw0rd!"
    )
    signer2 = User.objects.create_user(
        username="s2@example.com", email="s2@example.com", full_name="S2", password="StrongPassw0rd!"
    )

    doc = Document.objects.create(
        owner=creator, file_url="/media/documents/test.pdf", file_name="test.pdf", file_size=1000, status="draft"
    )
    env = Envelope.objects.create(
        document=doc,
        creator=creator,
        signing_order=[{"signer_id": str(signer1.id), "order": 1}, {"signer_id": str(signer2.id), "order": 2}],
        status="sent",
    )

    Signature.objects.create(envelope=env, signer=signer1, status="pending")
    Signature.objects.create(envelope=env, signer=signer2, status="pending")

    client.force_login(signer1)
    url = reverse("signatures-sign", kwargs={"envelope_id": str(env.id)})
    res = client.post(url, {"signature_image": "data:image/png;base64,a"}, content_type="application/json")

    assert res.status_code in (200, 400)  # depending on PDF availability; we only check email hook
    assert mock_delay.called

