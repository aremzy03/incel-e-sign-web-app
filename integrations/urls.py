"""
URL routes for first-party integrations.
"""

from django.urls import path

from integrations.views import TokenExchangeView
from integrations.views_envelopes import IntegrationEnvelopeSendView

app_name = "integrations"

urlpatterns = [
    path("token/", TokenExchangeView.as_view(), name="token_exchange"),
    path(
        "envelopes/send/",
        IntegrationEnvelopeSendView.as_view(),
        name="envelopes_send",
    ),
]
