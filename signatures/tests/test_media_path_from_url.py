"""
Tests for get_media_absolute_path_from_url (URL vs filesystem path alignment).
"""

import os

import pytest
from django.conf import settings

from signatures.utils.pdf_signing import get_media_absolute_path_from_url


@pytest.mark.django_db
def test_get_media_absolute_path_unquotes_percent_encoded_path(tmp_path):
    """FileSystemStorage.url() may emit %20; on-disk names use spaces."""
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    rel_fs = os.path.join("temp_uploads", "documents", "user_file with spaces.pdf")
    abs_fs = tmp_path / rel_fs
    abs_fs.parent.mkdir(parents=True, exist_ok=True)
    abs_fs.write_bytes(b"%PDF")

    file_url = "/media/temp_uploads/documents/user_file%20with%20spaces.pdf"
    resolved = get_media_absolute_path_from_url(file_url)
    assert resolved == str(abs_fs)
    assert os.path.exists(resolved)
