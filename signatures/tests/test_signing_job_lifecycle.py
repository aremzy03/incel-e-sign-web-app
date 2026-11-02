"""
End-to-end lifecycle tests for async signing jobs.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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


@pytest.mark.django_db
def test_signing_job_lifecycle_succeeds(settings, tmp_path):
    """Sign returns 202, eager worker completes job, signature becomes signed."""
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    User = get_user_model()
    creator = User.objects.create_user(
        email="creator@test.com", username="creator", full_name="Creator", password="pass1234"
    )
    signer = User.objects.create_user(
        email="signer@test.com", username="signer", full_name="Signer", password="pass1234"
    )

    rel = "staging/lifecycle.pdf"
    abs_pdf = tmp_path / rel
    abs_pdf.parent.mkdir(parents=True, exist_ok=True)
    abs_pdf.write_bytes(b"%PDF-1.4\n%EOF")

    doc = Document.objects.create(
        owner=creator,
        file_url=f"/media/{rel}",
        file_name="lifecycle.pdf",
        file_size=abs_pdf.stat().st_size,
        status="draft",
    )
    envelope = Envelope.objects.create(
        creator=creator,
        name="Lifecycle",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=1)
    signature = Signature.objects.create(envelope=envelope, signer=signer, status="pending")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(signer).access_token}")

    sign_resp = client.post(
        reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id}),
        {"signature_image": SIGNATURE_IMAGE},
        format="json",
    )
    assert sign_resp.status_code == status.HTTP_202_ACCEPTED
    job_id = sign_resp.data["data"]["job_id"]

    job = SigningJob.objects.get(pk=job_id)
    assert job.status == "succeeded"
    assert job.completed_at is not None

    signature.refresh_from_db()
    assert signature.status == "signed"
    assert signature.signed_at is not None

    detail_resp = client.get(reverse("signatures:signing-job-detail", kwargs={"id": job_id}))
    assert detail_resp.status_code == 200
    assert detail_resp.data["data"]["status"] == "succeeded"


@pytest.mark.django_db
def test_signing_job_retry_after_failure(monkeypatch, settings, tmp_path):
    """Failed jobs can be retried via the retry endpoint."""
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    User = get_user_model()
    signer = User.objects.create_user(
        email="signer@test.com", username="signer", full_name="Signer", password="pass1234"
    )

    rel = "staging/retry.pdf"
    abs_pdf = tmp_path / rel
    abs_pdf.parent.mkdir(parents=True, exist_ok=True)
    abs_pdf.write_bytes(b"%PDF-1.4\n%EOF")

    doc = Document.objects.create(
        owner=signer,
        file_url=f"/media/{rel}",
        file_name="retry.pdf",
        file_size=abs_pdf.stat().st_size,
        status="draft",
    )
    envelope = Envelope.objects.create(
        creator=signer,
        name="Retry",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=1)
    Signature.objects.create(envelope=envelope, signer=signer, status="pending")

    call_count = {"n": 0}
    from signatures.tasks import embed_envelope_document_for_signer as original

    def flaky_embed(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated embed failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "signatures.tasks.embed_envelope_document_for_signer",
        flaky_embed,
    )

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(signer).access_token}")

    sign_resp = client.post(
        reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id}),
        {"signature_image": SIGNATURE_IMAGE},
        format="json",
    )
    assert sign_resp.status_code == status.HTTP_202_ACCEPTED
    job_id = sign_resp.data["data"]["job_id"]

    job = SigningJob.objects.get(pk=job_id)
    assert job.status == "failed"

    retry_resp = client.post(reverse("signatures:signing-job-retry", kwargs={"id": job_id}))
    assert retry_resp.status_code == status.HTTP_202_ACCEPTED

    job.refresh_from_db()
    assert job.status == "succeeded"


@pytest.mark.django_db
def test_processing_signature_retains_current_signer_turn():
    """A signature in 'processing' status remains the current signer until completed."""
    from envelopes.serializers import _get_envelope_current_signer

    User = get_user_model()
    signer1 = User.objects.create_user(
        email="s1@test.com", username="s1", full_name="Signer One", password="pass1234"
    )
    signer2 = User.objects.create_user(
        email="s2@test.com", username="s2", full_name="Signer Two", password="pass1234"
    )

    envelope = Envelope.objects.create(
        creator=signer1,
        name="Multi Signer Turn Test",
        status="pending",
        signing_order=[
            {"signer_id": str(signer1.id), "order": 1},
            {"signer_id": str(signer2.id), "order": 2},
        ],
    )
    sig1 = Signature.objects.create(envelope=envelope, signer=signer1, status="processing")
    sig2 = Signature.objects.create(envelope=envelope, signer=signer2, status="pending")

    assert sig1.is_current_signer() is True
    assert sig2.is_current_signer() is False

    current = _get_envelope_current_signer(envelope)
    assert current is not None
    assert current["id"] == str(signer1.id)

