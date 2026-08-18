"""
Test settings for the E-Sign application.
"""

from .settings import *
from pathlib import Path

# Allow the Django test client host and common local hosts
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# Ensure media URLs are always local paths during tests.
# Some environments inject absolute URLs which can cause download endpoints
# to redirect (302) instead of streaming local files.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(BASE_DIR) / "test_media"

# Override Celery configuration for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Isolate test cache from shared Redis (production CACHES). Redis-backed
# UserRateThrottle / AnonRateThrottle state otherwise bleeds across tests and
# can surface as intermittent 401/429 / missing response `data` in full runs.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "esign-test-cache",
    }
}

# Disable global throttles for the suite; keep rate map so scoped throttles
# (auth / integration_token) remain configurable when a test opts into them.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/hour",
        "user": "10000/hour",
        "auth": "10000/minute",
        "upload": "10000/hour",
        "integration_token": "10000/minute",
    },
}

# All test envelopes use the async signing pipeline
from datetime import datetime, timezone as dt_timezone

SIGNING_CUTOVER_AT = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)

# Tests always use local filesystem storage, not live S3.
USE_S3 = False
ENVIRONMENT = "development"
AWS_LOCATION = "incel-esign-dev"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
