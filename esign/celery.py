"""
Celery application instance for the Django project.

This follows the common Django + Celery integration pattern so that
`celery -A esign worker --loglevel=info` works out of the box.
"""

import os
from celery import Celery

# Set default Django settings module for Celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign.settings")

# Explicitly include known task modules to guarantee registration
celery_app = Celery("esign", include=[
    "notifications.tasks",
])

# Read config from Django settings, using the `CELERY_` namespace
celery_app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed Django apps (kept for future apps)
celery_app.autodiscover_tasks()


