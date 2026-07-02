"""
Tests for S3/CloudFront URL refresh helpers used in API serializers.
"""

from unittest.mock import MagicMock, patch

import pytest

from documents.serializers import DocumentSerializer
from documents.storage import refresh_remote_file_url, storage_relative_key, persistable_storage_url


def test_persistable_storage_url_strips_signing_query_params():
    signed = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/"
        "11111111-1111-1111-1111-111111111111.pdf?Expires=999&Signature=abc&Key-Pair-Id=APKA"
    )
    assert persistable_storage_url(signed) == (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/"
        "11111111-1111-1111-1111-111111111111.pdf"
    )


def test_persistable_storage_url_leaves_local_paths_unchanged():
    assert persistable_storage_url("/media/staging/doc.pdf") == "/media/staging/doc.pdf"


def test_refresh_remote_file_url_normalizes_whitespace_hostname(settings):
    settings.USE_S3 = False
    dirty = "https://dijl0kmob0tbo.cloudfront.net   /incel-esign-app/staging/doc.pdf"
    assert refresh_remote_file_url(dirty) == (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/doc.pdf"
    )


def test_refresh_remote_file_url_returns_local_path_unchanged(settings):
    settings.USE_S3 = True
    url = "/media/temp_uploads/doc.pdf"
    assert refresh_remote_file_url(url) == url


def test_refresh_remote_file_url_skips_when_s3_disabled(settings):
    settings.USE_S3 = False
    url = "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/doc.pdf?Expires=1"
    assert refresh_remote_file_url(url) == url


def test_refresh_remote_file_url_regenerates_signed_url(settings):
    settings.USE_S3 = True
    stored_url = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/"
        "11111111-1111-1111-1111-111111111111.pdf?Expires=1&Signature=old"
    )
    fresh_url = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/staging/"
        "11111111-1111-1111-1111-111111111111.pdf?Expires=999&Signature=new"
    )

    mock_storage = MagicMock()
    mock_storage.url.return_value = fresh_url

    with patch("documents.storage.get_permanent_s3_storage", return_value=mock_storage):
        result = refresh_remote_file_url(stored_url)

    assert result == fresh_url
    mock_storage.url.assert_called_once_with(
        "staging/11111111-1111-1111-1111-111111111111.pdf"
    )


def test_storage_relative_key_strips_aws_location(settings):
    settings.AWS_LOCATION = "incel-esign-app"
    key = "incel-esign-app/completed/env/doc.pdf"
    assert storage_relative_key(key) == "completed/env/doc.pdf"


def test_storage_relative_key_leaves_relative_keys_unchanged(settings):
    settings.AWS_LOCATION = "incel-esign-app"
    key = "staging/doc.pdf"
    assert storage_relative_key(key) == key


def test_refresh_remote_file_url_avoids_double_location_prefix(settings):
    settings.USE_S3 = True
    settings.AWS_LOCATION = "incel-esign-app"
    stored_url = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/completed/"
        "634dd246-3035-40b3-9be1-993ca5377e64/a7ad8a85-3d53-49ae-8c13-b0a61523462b.pdf"
        "?Expires=1&Signature=old&Key-Pair-Id=K4JTP2OI1A4VT"
    )
    fresh_url = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/completed/"
        "634dd246-3035-40b3-9be1-993ca5377e64/a7ad8a85-3d53-49ae-8c13-b0a61523462b.pdf"
        "?Expires=999&Signature=new&Key-Pair-Id=K4JTP2OI1A4VT"
    )

    mock_storage = MagicMock()
    mock_storage.url.return_value = fresh_url

    with patch("documents.storage.get_permanent_s3_storage", return_value=mock_storage):
        result = refresh_remote_file_url(stored_url)

    assert result == fresh_url
    mock_storage.url.assert_called_once_with(
        "completed/634dd246-3035-40b3-9be1-993ca5377e64/"
        "a7ad8a85-3d53-49ae-8c13-b0a61523462b.pdf"
    )
    assert "/incel-esign-app/incel-esign-app/" not in result


@pytest.mark.django_db
def test_document_serializer_refreshes_remote_urls(settings):
    settings.USE_S3 = True

    from django.contrib.auth import get_user_model

    from documents.models import Document

    User = get_user_model()
    owner = User.objects.create_user(
        email="owner@test.com",
        username="owner",
        full_name="Owner",
        password="testpass123",
    )
    stored_url = (
        "https://dijl0kmob0tbo.cloudfront.net/incel-esign-app/completed/"
        "env/doc.pdf?Expires=1&Signature=old"
    )
    document = Document.objects.create(
        owner=owner,
        file_url=stored_url,
        signed_file_url=stored_url,
        file_name="doc.pdf",
        file_size=100,
        status="draft",
    )
    fresh_url = stored_url.replace("Expires=1", "Expires=999").replace("old", "new")

    with patch("documents.storage.get_permanent_s3_storage") as mock_get_storage:
        mock_get_storage.return_value.url.return_value = fresh_url
        data = DocumentSerializer(document).data

    assert data["file_url"] == fresh_url
    assert data["signed_file_url"] == fresh_url
    assert data["current_file_url"] == fresh_url
