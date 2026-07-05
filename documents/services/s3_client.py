"""
Boto3 S3 client factory with bounded connect/read timeouts for worker tasks.
"""

from __future__ import annotations

import boto3
from botocore.config import Config
from django.conf import settings


def get_boto3_s3_client():
    """
    Return an S3 client configured with short timeouts and limited retries.

    Prevents Celery signing tasks from hanging for many minutes on DNS or
    network failures while still allowing brief transient outage recovery.
    """
    connect_timeout = getattr(settings, "AWS_S3_CONNECT_TIMEOUT", 10)
    read_timeout = getattr(settings, "AWS_S3_READ_TIMEOUT", 60)
    max_attempts = getattr(settings, "AWS_S3_MAX_ATTEMPTS", 3)
    config = Config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_attempts, "mode": "standard"},
    )
    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION_NAME,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=config,
    )
