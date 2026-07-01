import os

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document


@pytest.mark.django_db
def test_document_upload_stores_locally_under_temp_uploads(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.TEMP_UPLOAD_SUBDIR = "temp_uploads"

    user = get_user_model().objects.create_user(
        email="u@test.com",
        username="u",
        full_name="User",
        password="testpass123",
    )

    token = str(RefreshToken.for_user(user).access_token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    pdf_bytes = b"%PDF-1.4\n%EOF"
    upload = SimpleUploadedFile("doc.pdf", pdf_bytes, content_type="application/pdf")

    resp = client.post(reverse("documents:document_upload"), {"file": upload}, format="multipart")
    assert resp.status_code == 201, resp.data

    doc_id = resp.data["data"]["id"]
    doc = Document.objects.get(id=doc_id)

    assert doc.file_url.startswith("/media/"), doc.file_url
    assert "/staging/" in doc.file_url, doc.file_url
    assert doc.signed_file_url in (None, ""), doc.signed_file_url

    rel_path = doc.file_url[len("/media/") :]
    abs_path = os.path.join(str(settings.MEDIA_ROOT), rel_path)
    assert os.path.exists(abs_path)

