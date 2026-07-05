"""
Tests for document preview access rules (signers vs owners).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.http import Http404
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from documents.views import get_accessible_document_for_user
from envelopes.models import Envelope, EnvelopeDocument


@pytest.mark.django_db
def test_get_accessible_document_treats_signer_id_as_string_like_detail_view():
    """
    DocumentDetailView compares str(signer_entry.get('signer_id')) to user id.
    Preview/download must do the same so UUID-typed signer_id still matches.
    """
    User = get_user_model()
    owner = User.objects.create_user(
        username="o@example.com",
        email="o@example.com",
        full_name="Owner",
        password="StrongPassw0rd!",
    )
    signer = User.objects.create_user(
        username="s@example.com",
        email="s@example.com",
        full_name="Signer",
        password="StrongPassw0rd!",
    )
    doc = Document.objects.create(
        owner=owner,
        file_url="/media/documents/x.pdf",
        file_name="x.pdf",
        file_size=1,
        status="draft",
    )

    env_doc = MagicMock()
    env_doc.envelope.signing_order = [{"signer_id": signer.id, "order": 1}]

    def _filter_envelope_documents(**kwargs):
        m = MagicMock()
        if kwargs.get("envelope__creator") is not None:
            m.exists.return_value = False
            return m
        m.select_related.return_value = [env_doc]
        return m

    with patch(
        "documents.views.EnvelopeDocument.objects.filter",
        side_effect=_filter_envelope_documents,
    ):
        resolved = get_accessible_document_for_user(signer, doc.id)
    assert resolved.id == doc.id


@pytest.mark.django_db
def test_get_accessible_raises_when_signer_id_uuid_does_not_match():
    """Wrong signer still raises Http404."""
    User = get_user_model()
    owner = User.objects.create_user(
        username="o2@example.com",
        email="o2@example.com",
        full_name="Owner",
        password="StrongPassw0rd!",
    )
    signer = User.objects.create_user(
        username="s2@example.com",
        email="s2@example.com",
        full_name="Signer",
        password="StrongPassw0rd!",
    )
    other = User.objects.create_user(
        username="x@example.com",
        email="x@example.com",
        full_name="Other",
        password="StrongPassw0rd!",
    )
    doc = Document.objects.create(
        owner=owner,
        file_url="/media/documents/y.pdf",
        file_name="y.pdf",
        file_size=1,
        status="draft",
    )

    env_doc = MagicMock()
    env_doc.envelope.signing_order = [{"signer_id": signer.id, "order": 1}]

    def _filter_envelope_documents(**kwargs):
        m = MagicMock()
        if kwargs.get("envelope__creator") is not None:
            m.exists.return_value = False
            return m
        m.select_related.return_value = [env_doc]
        return m

    with patch(
        "documents.views.EnvelopeDocument.objects.filter",
        side_effect=_filter_envelope_documents,
    ):
        with pytest.raises(Http404):
            get_accessible_document_for_user(other, doc.id)


@pytest.mark.django_db
def test_preview_allowed_for_envelope_signer(settings, tmp_path):
    """Signer listed on an envelope containing the document can GET preview (local file)."""
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    User = get_user_model()
    creator = User.objects.create_user(
        username="c@example.com",
        email="c@example.com",
        full_name="Creator",
        password="StrongPassw0rd!",
    )
    signer = User.objects.create_user(
        username="s3@example.com",
        email="s3@example.com",
        full_name="Signer",
        password="StrongPassw0rd!",
    )

    rel = "documents/preview_test.pdf"
    abs_pdf = tmp_path / rel
    abs_pdf.parent.mkdir(parents=True, exist_ok=True)
    abs_pdf.write_bytes(b"%PDF-1.4 minimal\n%%EOF")

    doc = Document.objects.create(
        owner=creator,
        file_url=f"/media/{rel}",
        file_name="preview_test.pdf",
        file_size=abs_pdf.stat().st_size,
        status="draft",
    )
    env = Envelope.objects.create(
        creator=creator,
        name="Env",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
        status="pending",
    )
    EnvelopeDocument.objects.create(envelope=env, document=doc, order=1)

    client = APIClient()
    token = str(RefreshToken.for_user(signer).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    url = reverse("documents:document_preview", kwargs={"pk": str(doc.id)})
    resp = client.get(url)
    try:
        assert resp.status_code == 200, getattr(resp, "data", resp.content[:200])
        assert resp["Content-Type"] == "application/pdf"
        assert os.path.exists(abs_pdf)
    finally:
        resp.close()
