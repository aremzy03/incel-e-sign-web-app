"""
Storage helpers for the documents app.

This module provides explicit storage backends for:
- temporary local file storage during signing workflows
- permanent S3 storage after envelope completion
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import clean_name


@deconstructible
class TimezoneAwareS3Boto3Storage(S3Boto3Storage):
    """
    S3 storage that signs CloudFront URLs with timezone-aware expiration.

    django-storages 1.14.6 still uses deprecated datetime.utcnow() when
    generating CloudFront signed URLs.
    """

    def url(self, name, parameters=None, expire=None, http_method=None):
        name = self._normalize_name(clean_name(name))
        params = parameters.copy() if parameters else {}
        if expire is None:
            expire = self.querystring_expire

        if self.custom_domain:
            url = "{}//{}/{}{}".format(
                self.url_protocol,
                self.custom_domain,
                filepath_to_uri(name),
                "?{}".format(urlencode(params)) if params else "",
            )

            if self.querystring_auth and self.cloudfront_signer:
                expiration = datetime.now(UTC) + timedelta(seconds=expire)
                return self.cloudfront_signer.generate_presigned_url(
                    url, date_less_than=expiration
                )

            return url

        return super().url(
            name,
            parameters=parameters,
            expire=expire,
            http_method=http_method,
        )


def get_temp_local_storage() -> FileSystemStorage:
    """
    Return a FileSystemStorage rooted at MEDIA_ROOT.

    This is used for temporary uploads and intermediate artifacts to keep
    signing read/write operations on local disk for performance.
    """
    return FileSystemStorage(location=str(settings.MEDIA_ROOT), base_url=settings.MEDIA_URL)


def get_permanent_s3_storage():
    """
    Return the configured S3 storage backend.

    Django-storages reads AWS_* settings from Django settings.
    """
    return TimezoneAwareS3Boto3Storage()


def storage_relative_key(key: str) -> str:
    """
    Return a storage-relative key suitable for S3Boto3Storage.url().

    resolve_s3_key_from_url() returns the full S3 object key (including AWS_LOCATION).
    django-storages prepends AWS_LOCATION again via _normalize_name(), so strip it first
    to avoid double-prefixed CloudFront paths.
    """
    if not key:
        return key

    location = getattr(settings, "AWS_LOCATION", "").strip("/")
    if not location:
        return key

    if key == location:
        return ""

    prefix = f"{location}/"
    if key.startswith(prefix):
        return key[len(prefix) :]

    return key


def persistable_storage_url(url: str) -> str:
    """
    Return a stable URL or path suitable for persisting on Document.

    Signed S3/CloudFront URLs include long-lived query parameters that can exceed
    database column limits. Callers should store this value and use
    refresh_remote_file_url() when returning URLs to clients.
    """
    if not url or not isinstance(url, str):
        return url
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return cleaned

    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(cleaned)
    netloc = parsed.netloc.strip()
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def normalize_remote_file_url(url: str | None) -> str | None:
    """
    Strip stray whitespace from persisted HTTP(S) file URLs.

    Common when AWS_S3_CUSTOM_DOMAIN was saved with trailing spaces before an
    inline .env comment, producing hosts like ``cdn.example.net   ``.
    """
    if not url or not isinstance(url, str):
        return url
    cleaned = url.strip()
    if not cleaned.startswith("http"):
        return cleaned

    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return cleaned
    netloc = parsed.netloc.strip()
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def refresh_remote_file_url(url: str | None) -> str | None:
    """
    Return a fresh S3 or CloudFront signed URL for browser access when USE_S3 is enabled.

    Stored URLs expire (AWS_QUERYSTRING_EXPIRE); API responses should call this so
    clients always receive a valid signed URL. Local /media paths are returned unchanged.

    Args:
        url: Persisted file URL from Document.file_url or Document.signed_file_url.

    Returns:
        A fresh signed URL when USE_S3 is enabled and the value is a remote HTTP(S) URL;
        otherwise the original url.
    """
    if not url:
        return url
    url = normalize_remote_file_url(url)
    if not getattr(settings, "USE_S3", False):
        return url
    if url.startswith("/media/") or not url.startswith("http"):
        return url

    from documents.services.pdf_files import resolve_s3_key_from_url

    try:
        key = resolve_s3_key_from_url(url)
    except ValueError:
        return url

    if not key:
        return url

    refreshed = get_permanent_s3_storage().url(storage_relative_key(key))
    return normalize_remote_file_url(refreshed)

