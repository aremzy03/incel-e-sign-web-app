"""
A signature is stamped once: failed jobs undo their partial work, re-runs skip finished
documents, retries and double submits can't add a second stamp.
"""

import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature, SigningJob

def _pdf_bytes() -> bytes:
    import fitz

    with fitz.open() as pdf:
        pdf.new_page()
        return pdf.tobytes()


SIGNATURE_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def two_doc_envelope(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    User = get_user_model()
    signer = User.objects.create_user(email="s@test.com", username="s", full_name="Signer", password="pass1234")
    envelope = Envelope.objects.create(
        creator=signer,
        name="Two docs",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    docs = []
    for order, name in enumerate(("a", "b"), 1):
        rel = f"staging/{name}.pdf"
        (tmp_path / "staging").mkdir(exist_ok=True)
        (tmp_path / rel).write_bytes(_pdf_bytes())
        doc = Document.objects.create(
            owner=signer, file_url=f"/media/{rel}", file_name=f"{name}.pdf", file_size=1, status="sent"
        )
        EnvelopeDocument.objects.create(envelope=envelope, document=doc, order=order)
        docs.append(doc)
    signature = Signature.objects.create(envelope=envelope, signer=signer, status="pending")
    return signer, envelope, docs, signature


def _fail_on_document(monkeypatch, failing_doc):
    from signatures.tasks import embed_envelope_document_for_signer as original

    def embed(envelope, signer, env_doc, *args, **kwargs):
        if env_doc.document_id == failing_doc.id:
            raise RuntimeError("simulated embed failure")
        return original(envelope, signer, env_doc, *args, **kwargs)

    monkeypatch.setattr("signatures.tasks.embed_envelope_document_for_signer", embed)


@pytest.mark.django_db
def test_failed_job_restores_documents_it_already_stamped(monkeypatch, two_doc_envelope):
    signer, envelope, (doc_a, doc_b), signature = two_doc_envelope
    original_a = doc_a.file_url
    _fail_on_document(monkeypatch, doc_b)

    resp = _client(signer).post(
        reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id}),
        {"signature_image": SIGNATURE_IMAGE},
        format="json",
    )
    assert resp.status_code == status.HTTP_202_ACCEPTED
    job = SigningJob.objects.get(pk=resp.data["data"]["job_id"])
    assert job.status == "failed"

    doc_a.refresh_from_db()
    assert doc_a.file_url == original_a
    assert doc_a.signed_file_url is None
    signature.refresh_from_db()
    assert signature.status == "pending"


@pytest.mark.django_db
def test_retry_after_partial_failure_stamps_each_document_once(monkeypatch, two_doc_envelope):
    signer, envelope, (doc_a, doc_b), signature = two_doc_envelope
    calls = []
    from signatures.tasks import embed_envelope_document_for_signer as original

    def embed(envelope, signer, env_doc, *args, **kwargs):
        calls.append(env_doc.document_id)
        if env_doc.document_id == doc_b.id and calls.count(doc_b.id) == 1:
            raise RuntimeError("simulated embed failure")
        return original(envelope, signer, env_doc, *args, **kwargs)

    monkeypatch.setattr("signatures.tasks.embed_envelope_document_for_signer", embed)
    client = _client(signer)
    resp = client.post(
        reverse("signatures:sign_document", kwargs={"envelope_id": envelope.id}),
        {"signature_image": SIGNATURE_IMAGE},
        format="json",
    )
    job_id = resp.data["data"]["job_id"]
    assert client.post(reverse("signatures:signing-job-retry", kwargs={"id": job_id})).status_code == 202

    job = SigningJob.objects.get(pk=job_id)
    assert job.status == "succeeded"
    # a: stamped, rolled back, stamped again on retry. Its final file has one stamp, from v1.
    doc_a.refresh_from_db()
    assert doc_a.file_url.endswith(f"signing/{envelope.id}/{doc_a.id}/v1.pdf") or "completed/" in doc_a.file_url
    assert calls.count(doc_a.id) == 2 and calls.count(doc_b.id) == 2


@pytest.mark.django_db
def test_redelivered_embed_skips_a_document_this_job_already_stamped(two_doc_envelope):
    from signatures.tasks import _record_document_sources, embed_document_for_signer

    signer, envelope, (doc_a, _doc_b), signature = two_doc_envelope
    job = SigningJob.objects.create(
        envelope=envelope, signer=signer, signature=signature, status="processing",
        signature_image_data=SIGNATURE_IMAGE,
    )
    _record_document_sources(job)
    env_doc = EnvelopeDocument.objects.get(envelope=envelope, document=doc_a)

    assert embed_document_for_signer.apply(args=(str(job.id), str(env_doc.id))).result["ok"]
    doc_a.refresh_from_db()
    stamped = doc_a.file_url
    assert stamped != "/media/staging/a.pdf"

    # The same task again (acks_late redelivery after a worker crash): nothing new.
    assert embed_document_for_signer.apply(args=(str(job.id), str(env_doc.id))).result["ok"]
    doc_a.refresh_from_db()
    assert doc_a.file_url == stamped


@pytest.mark.django_db
def test_retry_refuses_when_signature_is_already_signed(two_doc_envelope):
    signer, envelope, _docs, signature = two_doc_envelope
    signature.status = "signed"
    signature.save()
    job = SigningJob.objects.create(envelope=envelope, signer=signer, signature=signature, status="failed")

    resp = _client(signer).post(reverse("signatures:signing-job-retry", kwargs={"id": job.id}))

    assert resp.status_code == status.HTTP_409_CONFLICT
    signature.refresh_from_db()
    assert signature.status == "signed"
    job.refresh_from_db()
    assert job.status == "failed"


@pytest.mark.django_db
def test_retry_refuses_when_envelope_is_no_longer_pending(two_doc_envelope):
    signer, envelope, _docs, signature = two_doc_envelope
    envelope.status = "rejected"
    envelope.save()
    job = SigningJob.objects.create(envelope=envelope, signer=signer, signature=signature, status="failed")

    resp = _client(signer).post(reverse("signatures:signing-job-retry", kwargs={"id": job.id}))

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_public_sign_while_a_job_is_running_joins_it(two_doc_envelope):
    from envelopes.services.signing_token import get_or_create_signing_token

    signer, envelope, _docs, signature = two_doc_envelope
    signature.status = "processing"
    signature.save()
    running = SigningJob.objects.create(envelope=envelope, signer=signer, signature=signature, status="processing")
    token = get_or_create_signing_token(envelope, signer.email, signer)

    resp = APIClient().post(
        reverse("signatures:sign_document_public", kwargs={"envelope_id": envelope.id}),
        {"token": token.token, "signature_image": SIGNATURE_IMAGE},
        format="json",
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    assert resp.data["data"]["job_id"] == str(running.id)
    assert SigningJob.objects.filter(envelope=envelope).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("public", [False, True])
def test_decline_is_refused_while_signing_is_in_progress(two_doc_envelope, public):
    from envelopes.services.signing_token import get_or_create_signing_token

    signer, envelope, _docs, signature = two_doc_envelope
    signature.status = "processing"
    signature.save()
    if public:
        token = get_or_create_signing_token(envelope, signer.email, signer)
        resp = APIClient().post(
            reverse("signatures:decline_signature_public", kwargs={"envelope_id": envelope.id}),
            {"token": token.token},
            format="json",
        )
    else:
        resp = _client(signer).post(
            reverse("signatures:decline_signature", kwargs={"envelope_id": envelope.id}), {}, format="json"
        )

    assert resp.status_code == status.HTTP_409_CONFLICT
    envelope.refresh_from_db()
    assert envelope.status == "pending"


def test_signature_image_is_scaled_to_print_resolution():
    from PIL import Image

    from signatures.utils.pdf_signing import SIGNATURE_DPI, _fit_signature_image

    buffer = io.BytesIO()
    Image.new("RGBA", (1280, 746), (0, 0, 0, 0)).save(buffer, format="PNG")
    big = buffer.getvalue()

    fitted = _fit_signature_image(big, [{"width": 116, "height": 36}])

    with Image.open(io.BytesIO(fitted)) as image:
        assert image.height <= round(36 * SIGNATURE_DPI / 72)
        assert abs(image.width / image.height - 1280 / 746) < 0.02
        assert image.mode == "RGBA"


def test_small_or_unreadable_signature_images_are_left_alone():
    from PIL import Image

    from signatures.utils.pdf_signing import _fit_signature_image

    buffer = io.BytesIO()
    Image.new("RGB", (100, 40)).save(buffer, format="PNG")
    small = buffer.getvalue()
    assert _fit_signature_image(small, [{"width": 116, "height": 36}]) == small
    assert _fit_signature_image(b"not an image", [{"width": 116, "height": 36}]) == b"not an image"


@pytest.mark.django_db
def test_shrink_user_signatures_command_reports_then_applies(settings, tmp_path):
    from django.core.files.base import ContentFile
    from django.core.management import call_command
    from PIL import Image

    from signatures.models import UserSignature

    settings.MEDIA_ROOT = tmp_path
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
    user = get_user_model().objects.create_user(email="c@test.com", username="c", full_name="C", password="pass1234")
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 900), (120, 120, 120)).save(buffer, format="PNG")
    signature = UserSignature(user=user)
    signature.image.save("big.png", ContentFile(buffer.getvalue()), save=True)
    old_name = signature.image.name

    out = io.StringIO()
    call_command("shrink_user_signatures", stdout=out)
    assert "Would shrink 1 of 1" in out.getvalue()
    signature.refresh_from_db()
    assert signature.image.name == old_name  # report only

    call_command("shrink_user_signatures", "--apply", stdout=io.StringIO())
    signature.refresh_from_db()
    assert signature.image.name != old_name
    assert not (tmp_path / old_name).exists()
    with signature.image.open("rb") as handle, Image.open(handle) as stored:
        assert stored.size == (711, 400)
