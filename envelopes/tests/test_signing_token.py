"""
Tests for SigningToken model, services, and public signing endpoints.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from envelopes.models import Envelope, EnvelopeDocument, SigningToken
from documents.models import Document
from signatures.models import Signature, UserSignature
from envelopes.services.signing_token import (
    get_or_create_signing_token,
    validate_signing_token,
    mark_token_used,
    revoke_envelope_tokens,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def creator(db):
    return User.objects.create_user(
        username="creator",
        email="creator@example.com",
        password="password123",
        full_name="Creator User",
    )


@pytest.fixture
def signer_user(db):
    return User.objects.create_user(
        username="signer1",
        email="signer1@example.com",
        password="password123",
        full_name="Signer One",
    )


@pytest.fixture
def test_document(db, creator):
    return Document.objects.create(
        owner=creator,
        file_name="agreement.pdf",
        file_url="/media/documents/test.pdf",
        file_size=1024,
        status="sent",
    )


@pytest.fixture
def test_envelope(db, creator, signer_user, test_document):
    env = Envelope.objects.create(
        creator=creator,
        name="Contract Envelope",
        status="pending",
        signing_order=[{"signer_id": str(signer_user.id), "order": 1}],
    )
    EnvelopeDocument.objects.create(
        envelope=env,
        document=test_document,
        order=1,
        signer_document_positions=[
            {
                "signer_id": str(signer_user.id),
                "position": {"page": 1, "x": 100, "y": 100, "width": 120, "height": 40},
            }
        ],
    )
    Signature.objects.create(
        envelope=env,
        signer=signer_user,
        status="pending",
    )
    return env


@pytest.mark.django_db
def test_get_or_create_signing_token(test_envelope, signer_user):
    token1 = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)
    assert token1.token is not None
    assert token1.is_valid()
    assert token1.recipient_email == "signer1@example.com"
    assert token1.recipient_user == signer_user

    # Reusing active token
    token2 = get_or_create_signing_token(test_envelope, "signer1@example.com")
    assert token1.id == token2.id
    assert token1.token == token2.token


@pytest.mark.django_db
def test_validate_signing_token_lifecycle(test_envelope, signer_user):
    token = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)

    # Valid
    valid_token, err_code, _ = validate_signing_token(token.token, envelope_id=str(test_envelope.id))
    assert err_code is None
    assert valid_token.id == token.id

    # Wrong envelope
    _, err_code, _ = validate_signing_token(token.token, envelope_id=str(uuid.uuid4()))
    assert err_code == "ENVELOPE_MISMATCH"

    # Expired token
    token.expires_at = timezone.now() - timedelta(days=1)
    token.save()
    _, err_code, _ = validate_signing_token(token.token, envelope_id=str(test_envelope.id))
    assert err_code == "TOKEN_EXPIRED"

    # Revoked token
    token.expires_at = timezone.now() + timedelta(days=7)
    token.is_revoked = True
    token.save()
    _, err_code, _ = validate_signing_token(token.token, envelope_id=str(test_envelope.id))
    assert err_code == "TOKEN_REVOKED"

    # Used token
    token.is_revoked = False
    token.save()
    mark_token_used(token)
    _, err_code, _ = validate_signing_token(token.token, envelope_id=str(test_envelope.id))
    assert err_code == "TOKEN_ALREADY_USED"


@pytest.mark.django_db
def test_envelope_public_detail_view(api_client, test_envelope, signer_user):
    token = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)

    url = f"/api/envelopes/{test_envelope.id}/public/?token={token.token}"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["id"] == str(test_envelope.id)
    assert data["recipient"]["email"] == "signer1@example.com"
    assert data["recipient"]["is_current_signer"] is True
    assert len(data["documents"]) == 1


@pytest.mark.django_db
def test_envelope_public_detail_view_expired_token(api_client, test_envelope, signer_user):
    token = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)
    token.expires_at = timezone.now() - timedelta(days=1)
    token.save()

    url = f"/api/envelopes/{test_envelope.id}/public/?token={token.token}"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_410_GONE
    body = response.json()
    assert body["code"] == "TOKEN_EXPIRED"
    assert body["recipient_email"] == "signer1@example.com"


@pytest.mark.django_db
@patch("signatures.views.create_and_enqueue_signing_job")
def test_sign_document_public_view(mock_enqueue, api_client, test_envelope, signer_user):
    from unittest.mock import MagicMock
    mock_job = MagicMock()
    mock_job.id = uuid.uuid4()
    mock_job.status = "queued"
    mock_job.envelope_id = test_envelope.id
    mock_enqueue.return_value = mock_job

    token = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)

    url = f"/api/signatures/{test_envelope.id}/sign-public/"
    payload = {
        "token": token.token,
        "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "page": 1,
        "x": 100,
        "y": 100,
        "width": 120,
        "height": 40,
    }
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["status"] == "success"

    # Token must now be marked as used
    token.refresh_from_db()
    assert token.used_at is not None


@pytest.mark.django_db
def test_decline_signature_public_view(api_client, test_envelope, signer_user):
    token = get_or_create_signing_token(test_envelope, "signer1@example.com", signer_user)

    url = f"/api/signatures/{test_envelope.id}/decline-public/"
    response = api_client.post(
        url,
        {"token": token.token, "decline_message": "Need amendments before signing"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    test_envelope.refresh_from_db()
    assert test_envelope.status == "rejected"

    token.refresh_from_db()
    assert token.is_revoked is True
