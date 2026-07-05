import os
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope


class _FakeS3Storage:
    def __init__(self):
        self.saved = []

    def save(self, key, file_obj):
        file_obj.read()
        self.saved.append(key)
        return key

    def url(self, key):
        return f"https://fake-s3.local/{key}"


MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
)


def _embed_signature_side_effect(*args, **kwargs):
    output_path = kwargs.get("output_path")
    if output_path is None and len(args) >= 2:
        output_path = args[1]
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(MINIMAL_PDF_BYTES)


@pytest.mark.django_db
def test_on_final_sign_completion_uploads_locked_pdf_to_s3_and_updates_urls(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.TEMP_UPLOAD_SUBDIR = "temp_uploads"
    settings.TEMP_SIGNED_SUBDIR = "signed_docs"

    User = get_user_model()
    creator = User.objects.create_user(email="creator@test.com", username="creator", full_name="Creator", password="testpass123")
    signer = User.objects.create_user(email="signer@test.com", username="signer", full_name="Signer", password="testpass123")

    creator_token = str(RefreshToken.for_user(creator).access_token)
    signer_token = str(RefreshToken.for_user(signer).access_token)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {creator_token}")

    # Valid minimal PDF bytes (copied from integration test fixture)
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
        b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
    )
    upload = SimpleUploadedFile("doc.pdf", pdf_bytes, content_type="application/pdf")
    up_resp = client.post(reverse("documents:document_upload"), {"file": upload}, format="multipart")
    assert up_resp.status_code == 201, up_resp.data
    doc_id = up_resp.data["data"]["id"]

    env_data = {"document_ids": [doc_id], "signing_order": [{"signer_id": str(signer.id), "order": 1}]}
    create_resp = client.post(reverse("envelopes:envelope_create"), env_data, format="json")
    assert create_resp.status_code == 201, create_resp.data
    envelope_id = create_resp.data["data"]["id"]

    send_resp = client.post(reverse("envelopes:envelope_send", kwargs={"pk": envelope_id}))
    assert send_resp.status_code == 200, send_resp.data

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {signer_token}")

    sign_data = {
        "signature_image": "data:image/png;base64,dGVzdA==",
        "page": 1,
        "x": 100,
        "y": 100,
        "width": 120,
        "height": 40,
    }

    fake_storage = _FakeS3Storage()
    with patch("signatures.services.signing.upload_completed_pdf") as mock_upload_completed:
        mock_upload_completed.side_effect = lambda e, d, p: fake_storage.url(f"completed/{e}/{d}.pdf")
        with patch("signatures.utils.pdf_signing.embed_signature", side_effect=_embed_signature_side_effect):
            sign_resp = client.post(reverse("signatures:sign_document", kwargs={"envelope_id": envelope_id}), sign_data, format="json")
            assert sign_resp.status_code == 202, sign_resp.data

    env = Envelope.objects.get(id=envelope_id)
    assert env.status == "completed"

    doc = Document.objects.get(id=doc_id)
    assert doc.file_url.startswith("https://fake-s3.local/"), doc.file_url
    assert doc.signed_file_url == doc.file_url
    assert fake_storage.saved == []
    assert mock_upload_completed.called

