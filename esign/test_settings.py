"""
Test settings for the E-Sign application.
"""

from .settings import *

# Allow the Django test client host and common local hosts
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# Override Celery configuration for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
