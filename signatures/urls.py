"""
URL configuration for the signatures app.

This module defines URL patterns for signature-related endpoints
in the e-signature workflow.
"""

from django.urls import path
from . import views

app_name = 'signatures'

urlpatterns = [
    path('<uuid:envelope_id>/sign/', views.SignDocumentView.as_view(), name='sign_document'),
    path('<uuid:envelope_id>/decline/', views.DeclineSignatureView.as_view(), name='decline_signature'),
]
