"""
Upload rejects PDFs that could never be signed; previews cache by version and send safe
filenames; completing an envelope copies the signed file inside S3.
"""

import fitz
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _pdf(**save_kwargs) -> bytes:
    with fitz.open() as pdf:
        pdf.new_page()
        return pdf.tobytes(**save_kwargs)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        email="up@test.com", username="up", full_name="Up User", password="testpass123"
    )


@pytest.fixture
def local_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.USE_S3 = False
    return tmp_path


def _upload(user, name, data):
    return _client(user).post(
        reverse("documents:document_upload"),
        {"file": SimpleUploadedFile(name, data, content_type="application/pdf")},
        format="multipart",
    )


@pytest.mark.parametrize(
    "data, message",
    [
        (b"This is not a PDF file", "isn't a valid PDF"),
        (b"%PDF-1.7\nthis is not really a pdf at all", "damaged"),
        (
            _pdf(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user"),
            "password-protected",
        ),
    ],
)
def test_upload_rejects_pdfs_that_cannot_be_signed(user, local_media, data, message):
    resp = _upload(user, "doc.pdf", data)

    assert resp.status_code == 400
    assert message in str(resp.data["errors"]["file"])
    assert not Document.objects.filter(owner=user).exists()


def test_upload_accepts_permission_restricted_pdfs(user, local_media):
    # Restrictions-only encryption opens without a password: signing can read it.
    data = _pdf(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="", permissions=fitz.PDF_PERM_PRINT)

    resp = _upload(user, "restricted.pdf", data)

    assert resp.status_code == 201, resp.data


def test_failed_word_conversion_is_a_400_not_a_500(user, local_media, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("soffice crashed")

    monkeypatch.setattr("documents.utils.convert_word_to_pdf", fail)

    resp = _client(user).post(
        reverse("documents:document_upload"),
        {"file": SimpleUploadedFile("letter.docx", b"PK\x03\x04 fake", content_type="application/octet-stream")},
        format="multipart",
    )

    assert resp.status_code == 400
    assert "conversion failed" in str(resp.data["errors"])


def _document(user, local_media, name='Contrat "été".pdf'):
    (local_media / "staging").mkdir(exist_ok=True)
    (local_media / "staging" / "x.pdf").write_bytes(_pdf())
    return Document.objects.create(
        owner=user, file_url="/media/staging/x.pdf", file_name=name, file_size=1, status="draft"
    )


def test_versioned_preview_is_cacheable_and_unversioned_is_not(user, local_media):
    doc = _document(user, local_media, name="plain.pdf")
    client = _client(user)
    url = reverse("documents:document_preview", kwargs={"pk": doc.id})

    versioned = client.get(url, {"v": "2026-11-19T10:00:00Z"})
    unversioned = client.get(url)

    assert versioned.status_code == 200
    assert versioned["Cache-Control"] == "private, max-age=86400"
    assert unversioned["Cache-Control"] == "private, no-cache"


def test_preview_and_download_encode_unusual_filenames(user, local_media):
    doc = _document(user, local_media)
    client = _client(user)

    preview = client.get(reverse("documents:document_preview", kwargs={"pk": doc.id}))
    download = client.get(reverse("documents:document_download", kwargs={"pk": doc.id}))

    assert preview["Content-Disposition"] == "inline; filename*=utf-8''Contrat%20%22%C3%A9t%C3%A9%22.pdf"
    assert download["Content-Disposition"].startswith("attachment; filename*=utf-8''Contrat")


# --- Completed copies -------------------------------------------------------------------


class _FakeStorage:
    def __init__(self):
        self.names = set()

    def get_available_name(self, name):
        return name if name not in self.names else name.replace(".pdf", "_x.pdf")

    def url(self, name):
        return f"https://cdn.example.com/env/{name}?Signature=abc"


class _FakeS3:
    def __init__(self):
        self.copies = []

    def copy_object(self, **kwargs):
        self.copies.append(kwargs)


def test_completed_copy_happens_inside_s3(settings, monkeypatch):
    from documents.services import pdf_files

    settings.USE_S3 = True
    settings.AWS_STORAGE_BUCKET_NAME = "bucket"
    settings.AWS_LOCATION = "env"
    s3 = _FakeS3()
    monkeypatch.setattr(pdf_files, "get_boto3_s3_client", lambda: s3)
    monkeypatch.setattr(pdf_files, "get_permanent_s3_storage", _FakeStorage)

    url = pdf_files.copy_completed_pdf("E", "D", "https://cdn.example.com/env/signing/E/D/v1.pdf")

    assert url == "https://cdn.example.com/env/completed/E/D.pdf"
    assert s3.copies == [
        {
            "Bucket": "bucket",
            "Key": "env/completed/E/D.pdf",
            "CopySource": {"Bucket": "bucket", "Key": "env/signing/E/D/v1.pdf"},
            "MetadataDirective": "COPY",
        }
    ]


def test_completed_copy_is_skipped_for_local_files(settings):
    from documents.services.pdf_files import copy_completed_pdf

    settings.USE_S3 = False
    assert copy_completed_pdf("E", "D", "/media/signing/E/D/v1.pdf") is None


def test_password_lock_uses_aes_256(tmp_path):
    from pypdf import PdfReader

    from envelopes.utils.pdf_security import lock_pdf_with_password

    source = tmp_path / "in.pdf"
    source.write_bytes(_pdf())
    locked = lock_pdf_with_password(pdf_path=str(source), password="secret")

    reader = PdfReader(locked)
    assert reader.is_encrypted
    assert reader.trailer["/Encrypt"]["/V"] == 5  # AES-256
    assert reader.decrypt("secret")
