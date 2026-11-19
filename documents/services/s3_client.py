"""
Boto3 S3 client factory with bounded connect/read timeouts for worker tasks.
"""

from __future__ import annotations

import threading

import boto3
from botocore.config import Config
from django.conf import settings


# One client per configuration and process: creating a client costs ~0.1 s and each new
# client opens its own TLS connections (another ~0.5 s on the first request). boto3
# clients are thread-safe, so gunicorn threads and Celery tasks can share one.
_clients: dict[tuple, object] = {}
_lock = threading.Lock()


def get_boto3_s3_client():
    """
    Return an S3 client configured with short timeouts and limited retries.

    Prevents Celery signing tasks from hanging for many minutes on DNS or
    network failures while still allowing brief transient outage recovery.
    The client is reused while the settings stay the same.
    """
    connect_timeout = getattr(settings, "AWS_S3_CONNECT_TIMEOUT", 10)
    read_timeout = getattr(settings, "AWS_S3_READ_TIMEOUT", 60)
    max_attempts = getattr(settings, "AWS_S3_MAX_ATTEMPTS", 3)
    key = (
        settings.AWS_S3_REGION_NAME,
        settings.AWS_ACCESS_KEY_ID,
        settings.AWS_SECRET_ACCESS_KEY,
        connect_timeout,
        read_timeout,
        max_attempts,
    )
    with _lock:
        client = _clients.get(key)
        if client is None:
            config = Config(
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                retries={"max_attempts": max_attempts, "mode": "standard"},
            )
            client = boto3.client(
                "s3",
                region_name=settings.AWS_S3_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=config,
            )
            _clients.clear()  # settings changed: drop the old client
            _clients[key] = client
    return client
