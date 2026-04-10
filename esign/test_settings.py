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
