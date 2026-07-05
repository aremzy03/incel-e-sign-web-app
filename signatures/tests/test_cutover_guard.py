"""
Tests for signing cutover guard and frozen envelopes.
"""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone as dj_timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature
from signatures.services.cutover import FROZEN_ENVELOPE_MESSAGE, is_envelope_frozen


@pytest.mark.django_db
def test_is_envelope_frozen_before_cutover(settings):
    settings.SIGNING_CUTOVER_AT = dj_timezone.now() + timedelta(days=1)
    user = get_user_model().objects.create_user(
        email="u@test.com", username="u", full_name="U", password="pass1234"
    )
    envelope = Envelope.objects.create(
        creator=user,
        name="Old",
        status="pending",
        signing_order=[{"signer_id": str(user.id), "order": 1}],
    )
    assert is_envelope_frozen(envelope) is True


@pytest.mark.django_db
def test_sign_returns_409_for_frozen_envelope(settings):
    settings.SIGNING_CUTOVER_AT = dj_timezone.now() + timedelta(days=1)
    User = get_user_model()
    creator = User.objects.create_user(email="c@test.com", username="c", full_name="C", password="pass1234")
    signer = User.objects.create_user(email="s@test.com", username="s", full_name="S", password="pass1234")

    doc = Document.objects.create(
        owner=creator,
        file_url="/media/staging/doc.pdf",
        file_name="doc.pdf",
        file_size=10,
        status="sent",
    )
    envelope = Envelope.objects.create(
        creator=creator,
        name="Frozen",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=1)
    Signature.objects.create(envelope=envelope, signer=signer, status="pending")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(signer).access_token}")
    resp = client.post(
        reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id}),
        {"signature_image": "data:image/png;base64,dGVzdA=="},
        format="json",
    )
    assert resp.status_code == 409
    assert resp.data["message"] == FROZEN_ENVELOPE_MESSAGE
