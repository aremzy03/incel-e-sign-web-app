"""
Shared PDF file I/O helpers for S3 staging, signing, and completion workflows.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.files.base import ContentFile

from documents.services.s3_client import get_boto3_s3_client
from documents.storage import (
    get_permanent_s3_storage,
    get_temp_local_storage,
    persistable_storage_url,
    storage_relative_key,
)

LOGGER = logging.getLogger(__name__)


def build_staging_key(document_id) -> str:
    """Return S3/storage-relative key for a draft document."""
    prefix = getattr(settings, "STAGING_KEY_PREFIX", "staging")
    return f"{prefix}/{document_id}.pdf"


def build_signing_key(envelope_id, document_id, version: int) -> str:
    """Return storage key for an intermediate signing version."""
    return f"signing/{envelope_id}/{document_id}/v{version}.pdf"


def build_completed_key(envelope_id, document_id) -> str:
    """Return storage key for a completed envelope document."""
    return f"completed/{envelope_id}/{document_id}.pdf"


def resolve_s3_key_from_url(url: str) -> str:
    """
    Extract the S3 object key from a stored file URL.

    Handles virtual-hosted and path-style URLs and strips the bucket name when present.
    """
    if not url:
        raise ValueError("url is empty")

    if url.startswith("/media/"):
        return unquote(url[len("/media/"):])

    parsed = urlparse(url)
    encoded_path = parsed.path.lstrip("/")
    key = unquote(encoded_path)
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    if bucket and key:
        first, rest = (key.split("/", 1) + [""])[:2]
        if first == bucket and rest:
            key = rest
    return key


def _use_s3_storage() -> bool:
    return bool(getattr(settings, "USE_S3", False))


@contextmanager
def temp_pdf_file(suffix: str = ".pdf") -> Iterator[Path]:
    """Yield a temporary PDF path and ensure cleanup."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="esign_pdf_")
    os.close(fd)
    try:
        yield Path(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            LOGGER.warning("Failed to remove temp PDF %s", path)


def download_pdf_to_temp(source_url: str) -> Path:
    """
    Download or resolve a PDF to a local temporary file path.

    Caller is responsible for deleting the returned path when done.
    """
    if not source_url:
        raise FileNotFoundError("source_url is empty")

    if source_url.startswith("/media/") or (
        not source_url.startswith("http://") and not source_url.startswith("https://")
    ):
        from signatures.utils.pdf_signing import get_media_absolute_path_from_url

        abs_path = get_media_absolute_path_from_url(source_url)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Local PDF not found: {abs_path}")
        fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="esign_dl_")
        os.close(fd)
        shutil.copy2(abs_path, temp_path)
        return Path(temp_path)

    key = resolve_s3_key_from_url(source_url)
    if not key:
        raise FileNotFoundError(f"Unable to resolve S3 key from URL: {source_url}")

    s3_client = get_boto3_s3_client()
    fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="esign_s3_")
    os.close(fd)
    try:
        s3_client.download_file(settings.AWS_STORAGE_BUCKET_NAME, key, temp_path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    return Path(temp_path)


def _upload_file_to_key(local_path: str | Path, key: str) -> str:
    """Upload a local PDF to storage and return the URL to persist on Document."""
    local_path = str(local_path)
    if _use_s3_storage():
        storage = get_permanent_s3_storage()
        with open(local_path, "rb") as pdf_file:
            saved_key = storage.save(key, pdf_file)
        return persistable_storage_url(storage.url(saved_key))

    storage = get_temp_local_storage()
    with open(local_path, "rb") as pdf_file:
        saved_key = storage.save(key, ContentFile(pdf_file.read()))
    return persistable_storage_url(storage.url(saved_key))


def delete_storage_url(url: str | None) -> None:
    """Best-effort delete for a persisted storage URL or local media path."""
    if not url:
        return

    if url.startswith("/media/") or (
        not url.startswith("http://") and not url.startswith("https://")
    ):
        from signatures.utils.pdf_signing import get_media_absolute_path_from_url

        try:
            abs_path = get_media_absolute_path_from_url(url)
        except ValueError:
            return

        try:
            os.remove(abs_path)
        except FileNotFoundError:
            return
        except OSError:
            LOGGER.warning("Failed to delete local storage file %s", abs_path, exc_info=True)
        return

    try:
        key = resolve_s3_key_from_url(url)
    except ValueError:
        return

    if not key:
        return

    try:
        get_permanent_s3_storage().delete(storage_relative_key(key))
    except Exception:
        LOGGER.warning("Failed to delete remote storage file %s", url, exc_info=True)


def upload_staging_pdf(document_id, local_path: str | Path) -> str:
    """Upload a PDF to staging storage for a draft document."""
    key = build_staging_key(document_id)
    return _upload_file_to_key(local_path, key)


def upload_signing_version(envelope_id, document_id, version: int, local_path: str | Path) -> str:
    """Upload an intermediate signing version PDF."""
    key = build_signing_key(envelope_id, document_id, version)
    return _upload_file_to_key(local_path, key)


def upload_completed_pdf(envelope_id, document_id, local_path: str | Path) -> str:
    """Upload the final completed PDF for an envelope document."""
    key = build_completed_key(envelope_id, document_id)
    return _upload_file_to_key(local_path, key)


def next_signing_version(envelope_id, document_id) -> int:
    """Return the next signing version number for a document in an envelope."""
    from documents.models import Document

    doc = Document.objects.filter(id=document_id).first()
    if not doc:
        return 1
    source = doc.signed_file_url or doc.file_url or ""
    if f"signing/{envelope_id}/{document_id}/v" in source:
        try:
            version_part = source.rsplit("/v", 1)[-1]
            current = int(version_part.split(".", 1)[0])
            return current + 1
        except (ValueError, IndexError):
            pass
    return 1
