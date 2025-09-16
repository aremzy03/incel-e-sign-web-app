"""
Celery configuration for the E-Sign application.
"""

from __future__ import absolute_import, unicode_literals
import os
import sys
from celery import Celery

# Use test settings if running tests
if 'pytest' in sys.modules or 'test' in sys.argv:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign.test_settings")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign.settings")

app = Celery("esign")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
