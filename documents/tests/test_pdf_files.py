"""
Tests for shared PDF file helpers (staging upload/download).
"""

import os

import pytest
from django.conf import settings

from documents.services.pdf_files import (
    build_staging_key,
    download_pdf_to_temp,
    upload_staging_pdf,
)


@pytest.mark.django_db
def test_staging_upload_and_download_roundtrip(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.USE_S3 = False
    settings.STAGING_KEY_PREFIX = "staging"

    doc_id = "11111111-1111-1111-1111-111111111111"
    pdf_bytes = b"%PDF-1.4\n%EOF"

    staging_path = tmp_path / "input.pdf"
    staging_path.write_bytes(pdf_bytes)

    url = upload_staging_pdf(doc_id, staging_path)
    assert "/staging/" in url
    assert url.endswith(f"{doc_id}.pdf")

    downloaded = download_pdf_to_temp(url)
    try:
        assert downloaded.read_bytes() == pdf_bytes
    finally:
        os.remove(downloaded)


def test_build_staging_key():
    doc_id = "22222222-2222-2222-2222-222222222222"
    assert build_staging_key(doc_id) == f"staging/{doc_id}.pdf"
