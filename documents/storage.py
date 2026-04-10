"""
Storage helpers for the documents app.

This module provides explicit storage backends for:
- temporary local file storage during signing workflows
- permanent S3 storage after envelope completion
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage


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
    from storages.backends.s3boto3 import S3Boto3Storage

    return S3Boto3Storage()

