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


# --- Local cache of S3 downloads ---------------------------------------------------------


class FakeS3:
    """head_object / download_file over an in-memory bucket, counting calls."""

    def __init__(self):
        self.objects = {}
        self.heads = 0
        self.downloads = 0

    def put(self, key, data):
        import hashlib

        self.objects[key] = (data, f'"{hashlib.md5(data).hexdigest()}"')

    def head_object(self, Bucket, Key):
        self.heads += 1
        return {"ETag": self.objects[Key][1]}

    def download_file(self, bucket, key, path):
        self.downloads += 1
        with open(path, "wb") as handle:
            handle.write(self.objects[key][0])


@pytest.fixture
def fake_s3(settings, tmp_path, monkeypatch):
    settings.PDF_CACHE_DIR = str(tmp_path / "cache")
    settings.PDF_CACHE_MAX_BYTES = 10_000
    settings.AWS_STORAGE_BUCKET_NAME = "bucket"
    s3 = FakeS3()
    monkeypatch.setattr("documents.services.pdf_files.get_boto3_s3_client", lambda: s3)
    return s3


def _read(path):
    try:
        return path.read_bytes()
    finally:
        os.remove(path)


def test_second_download_is_served_locally_after_a_head_request(fake_s3):
    fake_s3.put("edits/doc/a.pdf", b"%PDF one")
    url = "https://cdn.example.com/edits/doc/a.pdf"
    assert _read(download_pdf_to_temp(url)) == b"%PDF one"
    # A signed URL for the same object hits the same entry.
    assert _read(download_pdf_to_temp(url + "?Signature=abc")) == b"%PDF one"
    assert (fake_s3.downloads, fake_s3.heads) == (1, 2)


def test_a_changed_object_is_downloaded_again(fake_s3):
    url = "https://cdn.example.com/staging/doc.pdf"
    fake_s3.put("staging/doc.pdf", b"%PDF old")
    _read(download_pdf_to_temp(url))
    fake_s3.put("staging/doc.pdf", b"%PDF new")
    assert _read(download_pdf_to_temp(url)) == b"%PDF new"
    assert fake_s3.downloads == 2


def test_an_upload_seeds_the_cache(fake_s3, tmp_path):
    from documents.services.pdf_files import remember_uploaded_pdf

    local = tmp_path / "out.pdf"
    local.write_bytes(b"%PDF baked")
    fake_s3.put("edits/doc/b.pdf", b"%PDF baked")
    remember_uploaded_pdf("https://cdn.example.com/edits/doc/b.pdf", local)
    assert _read(download_pdf_to_temp("https://cdn.example.com/edits/doc/b.pdf")) == b"%PDF baked"
    assert fake_s3.downloads == 0


def test_the_cache_drops_least_recently_used_copies(fake_s3):
    for name in ("one", "two", "three"):
        fake_s3.put(f"k/{name}.pdf", name.encode() * 1500)  # ~4.5-7.5 KB each, limit 10 KB
        _read(download_pdf_to_temp(f"https://cdn.example.com/k/{name}.pdf"))
    cached = [n for n in os.listdir(settings.PDF_CACHE_DIR) if n.endswith(".pdf")]
    assert len(cached) == 1
    fake_s3.downloads = 0
    _read(download_pdf_to_temp("https://cdn.example.com/k/three.pdf"))
    assert fake_s3.downloads == 0


def test_cache_off_downloads_every_time(fake_s3, settings):
    settings.PDF_CACHE_MAX_BYTES = 0
    fake_s3.put("k/x.pdf", b"%PDF x")
    for _ in range(2):
        _read(download_pdf_to_temp("https://cdn.example.com/k/x.pdf"))
    assert (fake_s3.downloads, fake_s3.heads) == (2, 0)
