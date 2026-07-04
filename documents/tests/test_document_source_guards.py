import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfWriter
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from documents.services.document_creation import create_draft_document_from_local_pdf


def _make_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _write_valid_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as pdf_file:
        writer.write(pdf_file)


def _raise_storage_error(*args, **kwargs):
    raise RuntimeError("storage unavailable")


@pytest.mark.django_db
def test_document_model_rejects_blank_file_url():
    user = get_user_model().objects.create_user(
        email="guard@test.com",
        username="guard",
        full_name="Guard User",
        password="testpass123",
    )

    with pytest.raises(ValidationError):
        Document.objects.create(
            owner=user,
            file_url="   ",
            file_name="broken.pdf",
            file_size=1,
            status="draft",
        )


@pytest.mark.django_db
def test_document_upload_failure_does_not_leave_orphan_row(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    user = get_user_model().objects.create_user(
        email="upload@test.com",
        username="upload",
        full_name="Upload User",
        password="testpass123",
    )
    client = _make_client(user)

    monkeypatch.setattr("documents.services.document_creation.upload_staging_pdf", _raise_storage_error)

    upload = SimpleUploadedFile("doc.pdf", b"%PDF-1.4\n%EOF", content_type="application/pdf")
    response = client.post(reverse("documents:document_upload"), {"file": upload}, format="multipart")

    assert response.status_code == 500, response.data
    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_create_draft_document_cleanup_runs_when_db_save_fails(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    user = get_user_model().objects.create_user(
        email="cleanup@test.com",
        username="cleanup",
        full_name="Cleanup User",
        password="testpass123",
    )

    local_pdf = tmp_path / "source.pdf"
    _write_valid_pdf(local_pdf)
    document_id = uuid.uuid4()

    with patch(
        "documents.services.document_creation.Document.objects.create",
        side_effect=RuntimeError("db unavailable"),
    ):
        with pytest.raises(RuntimeError):
            create_draft_document_from_local_pdf(
                owner=user,
                file_name="cleanup.pdf",
                local_path=local_pdf,
                file_size=local_pdf.stat().st_size,
                document_id=document_id,
            )

    expected_staging_path = tmp_path / "staging" / f"{document_id}.pdf"
    assert not expected_staging_path.exists()
    assert not Document.objects.filter(id=document_id).exists()


@pytest.mark.django_db
def test_merge_failure_does_not_leave_orphan_row(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    user = get_user_model().objects.create_user(
        email="merge@test.com",
        username="merge",
        full_name="Merge User",
        password="testpass123",
    )
    client = _make_client(user)

    rel_one = "documents/merge-one.pdf"
    rel_two = "documents/merge-two.pdf"
    abs_one = tmp_path / rel_one
    abs_two = tmp_path / rel_two
    abs_one.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_pdf(abs_one)
    _write_valid_pdf(abs_two)

    doc_one = Document.objects.create(
        owner=user,
        file_url=f"/media/{rel_one}",
        file_name="merge-one.pdf",
        file_size=abs_one.stat().st_size,
        status="draft",
    )
    doc_two = Document.objects.create(
        owner=user,
        file_url=f"/media/{rel_two}",
        file_name="merge-two.pdf",
        file_size=abs_two.stat().st_size,
        status="draft",
    )

    monkeypatch.setattr("documents.services.document_creation.upload_staging_pdf", _raise_storage_error)

    response = client.post(
        reverse("documents:documents-merge"),
        {"document_ids": [str(doc_one.id), str(doc_two.id)]},
        format="json",
    )

    assert response.status_code == 500, response.data
    assert Document.objects.count() == 2


@pytest.mark.django_db
def test_preview_returns_404_for_legacy_document_with_missing_source_url(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    user = get_user_model().objects.create_user(
        email="preview@test.com",
        username="preview",
        full_name="Preview User",
        password="testpass123",
    )
    client = _make_client(user)

    rel = "documents/legacy-preview.pdf"
    abs_pdf = tmp_path / rel
    abs_pdf.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_pdf(abs_pdf)

    doc = Document.objects.create(
        owner=user,
        file_url=f"/media/{rel}",
        file_name="legacy-preview.pdf",
        file_size=abs_pdf.stat().st_size,
        status="draft",
    )

    Document.objects.filter(pk=doc.pk).update(file_url="")

    response = client.get(reverse("documents:document_preview", kwargs={"pk": str(doc.id)}))

    assert response.status_code == 404, response.data
    assert response.data["message"] == "Document file reference is missing"


@pytest.mark.django_db
def test_download_streams_remote_document_via_shared_s3_client(settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"

    user = get_user_model().objects.create_user(
        email="download@test.com",
        username="download",
        full_name="Download User",
        password="testpass123",
    )
    client = _make_client(user)

    doc = Document.objects.create(
        owner=user,
        file_url="https://test-bucket.s3.amazonaws.com/documents/remote.pdf",
        file_name="remote.pdf",
        file_size=10,
        status="draft",
    )

    body = MagicMock()
    body.iter_chunks.return_value = [b"%PDF-1.4\n", b"%%EOF"]
    s3_client = MagicMock()
    s3_client.get_object.return_value = {
        "Body": body,
        "ContentType": "application/pdf",
        "ContentLength": 12,
    }

    with patch("documents.views.get_boto3_s3_client", return_value=s3_client):
        response = client.get(reverse("documents:document_download", kwargs={"pk": str(doc.id)}))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'attachment; filename="remote.pdf"'
    assert b"".join(response.streaming_content) == b"%PDF-1.4\n%%EOF"
    s3_client.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="documents/remote.pdf",
    )
