"""
Tests for edit/resend reset behavior.

Ensures that after a rejected envelope is edited and re-sent:
- Signatures are rebuilt from the new signing_order and current_signer is the new first signer.
- PDFs are reset back to staging originals (Document.file_url points to staging and signed_file_url cleared).
- Edit/send are blocked while a SigningJob is queued/processing.
"""

import os
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature, SigningJob


SIGNATURE_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _auth_client(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_rejected_edit_resend_resets_signatures_and_pdfs(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.USE_S3 = False
    settings.CELERY_TASK_ALWAYS_EAGER = True

    User = get_user_model()
    creator = User.objects.create_user(
        email="creator@test.com", username="creator", full_name="Creator", password="pass1234"
    )
    signer1 = User.objects.create_user(
        email="signer1@test.com", username="signer1", full_name="Signer1", password="pass1234"
    )
    signer2 = User.objects.create_user(
        email="signer2@test.com", username="signer2", full_name="Signer2", password="pass1234"
    )
    signer3 = User.objects.create_user(
        email="signer3@test.com", username="signer3", full_name="Signer3", password="pass1234"
    )

    # Create a staging PDF for the document at /media/staging/<doc_id>.pdf
    doc_id = uuid.uuid4()
    staging_rel = f"staging/{doc_id}.pdf"
    doc = Document.objects.create(
        id=doc_id,
        owner=creator,
        file_url=f"/media/{staging_rel}",
        file_name="test.pdf",
        file_size=10,
        status="draft",
    )
    staging_abs = tmp_path / staging_rel
    staging_abs.parent.mkdir(parents=True, exist_ok=True)
    staging_abs.write_bytes(b"%PDF-1.4\n%EOF")

    envelope = Envelope.objects.create(
        creator=creator,
        name="ResetFlow",
        status="draft",
        signing_order=[
            {"signer_id": str(signer1.id), "order": 1},
            {"signer_id": str(signer2.id), "order": 2},
        ],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=1)

    creator_client = _auth_client(creator)
    signer1_client = _auth_client(signer1)

    # Initial send (creates pending envelope + signatures)
    send_url = reverse("envelopes:envelope_send", kwargs={"pk": envelope.id})
    send_resp = creator_client.post(send_url)
    assert send_resp.status_code == status.HTTP_200_OK

    envelope.refresh_from_db()
    assert envelope.status == "pending"

    # Signer1 signs -> worker should update Document.file_url to signing/<envelope>/<doc>/v1.pdf
    sign_url = reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id})
    sign_resp = signer1_client.post(sign_url, {"signature_image": SIGNATURE_IMAGE}, format="json")
    assert sign_resp.status_code == status.HTTP_202_ACCEPTED

    doc.refresh_from_db()
    assert f"/signing/{envelope.id}/{doc.id}/v" in (doc.signed_file_url or doc.file_url)

    # Creator rejects envelope
    reject_url = reverse("envelopes:envelope_reject", kwargs={"pk": envelope.id})
    reject_resp = creator_client.post(reject_url)
    assert reject_resp.status_code == status.HTTP_200_OK

    envelope.refresh_from_db()
    assert envelope.status == "rejected"

    # Edit: change first signer to signer3, keep signer2 second
    edit_url = reverse("envelopes:envelope_edit", kwargs={"pk": envelope.id})
    edit_payload = {
        "signing_order": [
            {"signer_id": str(signer3.id), "order": 1},
            {"signer_id": str(signer2.id), "order": 2},
        ]
    }
    edit_resp = creator_client.patch(edit_url, edit_payload, format="json")
    assert edit_resp.status_code == status.HTTP_200_OK

    envelope.refresh_from_db()
    assert envelope.status == "draft"

    # Resend triggers reset_signing_workflow: signatures rebuilt + PDFs reset to staging
    resend_resp = creator_client.post(send_url)
    assert resend_resp.status_code == status.HTTP_200_OK

    envelope.refresh_from_db()
    assert envelope.status == "pending"

    signatures = list(Signature.objects.filter(envelope=envelope).order_by("created_at"))
    assert len(signatures) == 2
    assert {str(sig.signer_id) for sig in signatures} == {str(signer2.id), str(signer3.id)}
    assert all(sig.status == "pending" for sig in signatures)

    detail_data = resend_resp.data["data"]
    assert detail_data["current_signer"]["id"] == str(signer3.id)

    # PDFs reset: document points back to staging and signed_file_url cleared
    doc.refresh_from_db()
    assert doc.signed_file_url is None
    assert doc.file_url.endswith(f"/staging/{doc.id}.pdf")

    # Signing artifacts cleaned up locally (best-effort): signing/<envelope>/<doc>/ should be removed.
    signing_dir = tmp_path / "signing" / str(envelope.id) / str(doc.id)
    assert not signing_dir.exists()


@pytest.mark.django_db
def test_edit_and_send_blocked_when_signing_job_inflight(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.USE_S3 = False

    User = get_user_model()
    creator = User.objects.create_user(
        email="creator@test.com", username="creator", full_name="Creator", password="pass1234"
    )
    signer = User.objects.create_user(
        email="signer@test.com", username="signer", full_name="Signer", password="pass1234"
    )

    doc = Document.objects.create(
        owner=creator,
        file_url="/media/staging/dummy.pdf",
        file_name="dummy.pdf",
        file_size=10,
        status="draft",
    )
    envelope = Envelope.objects.create(
        creator=creator,
        name="Inflight",
        status="rejected",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=1)

    # In-flight job
    SigningJob.objects.create(
        envelope=envelope,
        signer=signer,
        status="processing",
    )

    creator_client = _auth_client(creator)

    edit_url = reverse("envelopes:envelope_edit", kwargs={"pk": envelope.id})
    edit_resp = creator_client.patch(
        edit_url,
        {"signing_order": [{"signer_id": str(signer.id), "order": 1}]},
        format="json",
    )
    assert edit_resp.status_code == status.HTTP_409_CONFLICT

    send_url = reverse("envelopes:envelope_send", kwargs={"pk": envelope.id})
    send_resp = creator_client.post(send_url)
    assert send_resp.status_code == status.HTTP_409_CONFLICT

