"""
Deprecated: Celery app moved to `esign/celery.py`.

Left in place to avoid import errors; please import from `esign` instead.
"""

from esign.celery import celery_app as app  # noqa: F401
