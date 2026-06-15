import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature


@pytest.mark.django_db
@patch("notifications.tasks.send_turn_to_sign_email_task.delay")
@patch("signatures.services.signing.embed_signature")
@patch("signatures.services.signing.os.path.exists", return_value=True)
def test_signing_triggers_next_signer_email(mock_exists, mock_embed, mock_delay):
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
        creator=creator,
        name="Test Envelope",
        signing_order=[{"signer_id": str(signer1.id), "order": 1}, {"signer_id": str(signer2.id), "order": 2}],
        status="pending",
    )
    EnvelopeDocument.objects.create(envelope=env, document=doc, order=1)

    Signature.objects.create(envelope=env, signer=signer1, status="pending")
    Signature.objects.create(envelope=env, signer=signer2, status="pending")

    # Use APIClient with JWT authentication
    api_client = APIClient()
    refresh = RefreshToken.for_user(signer1)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    # Valid small base64 PNG image
    import base64
    tiny_png = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100).decode()
    url = reverse("signatures:sign_document", kwargs={"envelope_id": str(env.id)})
    res = api_client.post(url, {"signature_image": f"data:image/png;base64,{tiny_png}"}, format="json")

    assert res.status_code == 200, f"Expected 200 but got {res.status_code}: {res.data}"
    assert mock_delay.called

