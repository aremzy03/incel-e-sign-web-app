"""
Shared PDF file I/O helpers for S3 staging, signing, and completion workflows.
"""

from __future__ import annotations

import hashlib
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
    absolute_s3_key,
    get_permanent_s3_storage,
    get_temp_local_storage,
    get_unprefixed_s3_storage,
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


# --- Local copies of stored PDFs ------------------------------------------------------
#
# A text edit used to download the same file three times: to open the session, to
# check it on save, and again to rewrite it, then once more when the editor reopened
# the session on the file it had just uploaded. Each download is a full S3 transfer.
# Stored files are never overwritten in place (AWS_S3_FILE_OVERWRITE is False; text
# edits and signing write new keys), and a cached copy is still checked against the
# object's ETag (a HEAD request, no body) before it is used, so a stale copy is never
# served. Uploads seed the cache, so the next step reads the file it just wrote.


def _cache_dir() -> str | None:
    if not getattr(settings, "PDF_CACHE_MAX_BYTES", 256 * 1024 * 1024):
        return None
    path = getattr(settings, "PDF_CACHE_DIR", None) or os.path.join(tempfile.gettempdir(), "esign-pdf-cache")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_entry(url: str) -> tuple[str, str] | None:
    directory = _cache_dir()
    if directory is None:
        return None
    # By object key: a CloudFront URL, an S3 URL and a signed URL for one file share an entry.
    try:
        key = resolve_s3_key_from_url(url)
    except ValueError:
        return None
    if not key:
        return None
    name = hashlib.sha256(key.encode()).hexdigest()
    return os.path.join(directory, f"{name}.pdf"), os.path.join(directory, f"{name}.etag")


def _copy_to_temp(path: str, prefix: str) -> Path:
    fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix=prefix)
    os.close(fd)
    shutil.copyfile(path, temp_path)
    return Path(temp_path)


def _store_in_cache(url: str, local_path: str | Path, etag: str | None) -> None:
    entry = _cache_entry(url)
    if entry is None or not etag:
        return
    pdf_path, etag_path = entry
    try:
        directory = os.path.dirname(pdf_path)
        fd, staging = tempfile.mkstemp(dir=directory, suffix=".part")
        os.close(fd)
        shutil.copyfile(local_path, staging)
        # Atomic: another worker reading at the same time sees the old copy or the new one.
        os.replace(staging, pdf_path)
        with open(etag_path, "w", encoding="ascii") as handle:
            handle.write(etag)
        _prune_cache(directory)
    except OSError:
        LOGGER.warning("Could not cache PDF %s", url, exc_info=True)


def _prune_cache(directory: str) -> None:
    """Drop the least recently used copies once the cache is over its size limit."""
    limit = getattr(settings, "PDF_CACHE_MAX_BYTES", 256 * 1024 * 1024)
    entries = []
    for name in os.listdir(directory):
        if name.endswith(".pdf"):
            path = os.path.join(directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
    total = sum(size for _mtime, size, _path in entries)
    for _mtime, size, path in sorted(entries):
        if total <= limit:
            break
        for victim in (path, path[: -len(".pdf")] + ".etag"):
            try:
                os.remove(victim)
            except OSError:
                pass
        total -= size


def _file_etag(path: str | Path) -> str:
    """S3's ETag for a single-part upload: the quoted MD5 of the bytes."""
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f'"{digest.hexdigest()}"'


def remember_uploaded_pdf(url: str, local_path: str | Path) -> None:
    """Seed the cache with a file just uploaded to ``url``, so reading it back costs a HEAD request."""
    if url.startswith(("http://", "https://")):
        try:
            _store_in_cache(url, local_path, _file_etag(local_path))
        except OSError:
            pass


def download_pdf_to_temp(source_url: str) -> Path:
    """
    Download or resolve a PDF to a local temporary file path.

    Caller is responsible for deleting the returned path when done. Remote files are
    served from a local copy when its ETag still matches the stored object.
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
    entry = _cache_entry(source_url)
    etag = None
    if entry is not None:
        try:
            etag = s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key).get("ETag")
        except Exception:
            etag = None  # the download below reports a missing object properly
        pdf_path, etag_path = entry
        try:
            with open(etag_path, encoding="ascii") as handle:
                cached = handle.read().strip()
            if etag and cached == etag and os.path.exists(pdf_path):
                os.utime(pdf_path)  # most recently used
                return _copy_to_temp(pdf_path, "esign_s3_")
        except OSError:
            pass

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
    _store_in_cache(source_url, temp_path, etag)
    return Path(temp_path)


def _upload_file_to_key(local_path: str | Path, key: str) -> str:
    """Upload a local PDF to storage and return the URL to persist on Document."""
    local_path = str(local_path)
    if _use_s3_storage():
        storage = get_permanent_s3_storage()
        with open(local_path, "rb") as pdf_file:
            saved_key = storage.save(key, pdf_file)
        url = persistable_storage_url(storage.url(saved_key))
        remember_uploaded_pdf(url, local_path)
        return url

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
        # The full stored key: the file may predate the current AWS_LOCATION prefix.
        get_unprefixed_s3_storage().delete(key)
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


def build_text_edit_key(document_id, session_id) -> str:
    """Return a new storage key for one additive-text commit. Never overwrites staging."""
    return f"edits/{document_id}/{session_id}.pdf"


def upload_text_edit_pdf(document_id, session_id, local_path: str | Path) -> str:
    """Upload a baked text-edit PDF without replacing the original object."""
    key = build_text_edit_key(document_id, session_id)
    return _upload_file_to_key(local_path, key)


def upload_completed_pdf(envelope_id, document_id, local_path: str | Path) -> str:
    """Upload the final completed PDF for an envelope document."""
    key = build_completed_key(envelope_id, document_id)
    return _upload_file_to_key(local_path, key)


def copy_completed_pdf(envelope_id, document_id, source_url: str) -> str | None:
    """
    Copy a stored PDF to its completed key inside S3 (no download, no upload).

    Completing an envelope without a password changes no bytes, so this replaces a full
    download and re-upload with one CopyObject request. Returns None when the source
    isn't an S3 object (the caller then uploads as before).
    """
    if not _use_s3_storage() or not source_url.startswith(("http://", "https://")):
        return None
    source_key = resolve_s3_key_from_url(source_url)
    if not source_key:
        return None
    storage = get_permanent_s3_storage()
    name = storage.get_available_name(build_completed_key(envelope_id, document_id))
    target_key = absolute_s3_key(storage_relative_key(name))
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    get_boto3_s3_client().copy_object(
        Bucket=bucket,
        Key=target_key,
        CopySource={"Bucket": bucket, "Key": source_key},
        MetadataDirective="COPY",
    )
    url = persistable_storage_url(storage.url(name))
    # Same bytes, same ETag: the cached copy of the source serves the new key too.
    entry = _cache_entry(source_url)
    if entry is not None:
        try:
            with open(entry[1], encoding="ascii") as handle:
                _store_in_cache(url, entry[0], handle.read().strip())
        except OSError:
            pass
    return url


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
