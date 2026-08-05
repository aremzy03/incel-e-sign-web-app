"""
Django app configuration for first-party server-to-server integrations.
"""

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """
    Configuration class for the integrations app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"
    verbose_name = "Integrations"
