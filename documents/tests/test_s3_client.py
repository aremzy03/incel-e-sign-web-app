"""Tests for the shared boto3 S3 client factory."""


from documents.services.s3_client import get_boto3_s3_client


def test_get_boto3_s3_client_uses_bounded_timeouts(settings):
    settings.AWS_S3_CONNECT_TIMEOUT = 7
    settings.AWS_S3_READ_TIMEOUT = 42
    settings.AWS_S3_MAX_ATTEMPTS = 2
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_ACCESS_KEY_ID = "test-key"
    settings.AWS_SECRET_ACCESS_KEY = "test-secret"

    client = get_boto3_s3_client()

    assert client.meta.config.connect_timeout == 7
    assert client.meta.config.read_timeout == 42
