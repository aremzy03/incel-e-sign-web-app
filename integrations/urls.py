"""
URL routes for first-party integrations.
"""

from django.urls import path

from integrations.views import TokenExchangeView

app_name = "integrations"

urlpatterns = [
    path("token/", TokenExchangeView.as_view(), name="token_exchange"),
]
