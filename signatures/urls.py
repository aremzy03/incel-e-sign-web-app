"""
URL configuration for the signatures app.

This module defines URL patterns for signature-related endpoints
in the e-signature workflow.
"""

from django.urls import path
from . import views

app_name = 'signatures'

urlpatterns = [
    # User signature management
    path('user/', views.UserSignatureListCreateView.as_view(), name='user-signatures'),
    path('user/<uuid:id>/', views.UserSignatureDetailView.as_view(), name='user-signature-detail'),

    # Async signing jobs
    path('jobs/<uuid:id>/', views.SigningJobDetailView.as_view(), name='signing-job-detail'),
    path('jobs/<uuid:id>/retry/', views.SigningJobRetryView.as_view(), name='signing-job-retry'),
    
    # Document signing
    path('self-sign/', views.SelfSignView.as_view(), name='self_sign'),
    path('<uuid:envelope_id>/sign/', views.SignDocumentView.as_view(), name='sign_document'),
    path('<uuid:envelope_id>/decline/', views.DeclineSignatureView.as_view(), name='decline_signature'),
]
