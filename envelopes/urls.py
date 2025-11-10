"""
URL configuration for the envelopes app.

This module defines URL patterns for envelope-related endpoints
in the e-signature workflow.
"""

from django.urls import path
from . import views

app_name = 'envelopes'

urlpatterns = [
    path('', views.EnvelopeListView.as_view(), name='envelope_list'),
    path('metrics/', views.EnvelopeMetricsView.as_view(), name='envelope_metrics'),
    path('<uuid:pk>/', views.EnvelopeDetailView.as_view(), name='envelope_detail'),
    path('<uuid:pk>/document/', views.EnvelopeDocumentView.as_view(), name='envelope_document'),
    path('create/', views.EnvelopeCreateView.as_view(), name='envelope_create'),
    path('<uuid:pk>/send/', views.EnvelopeSendView.as_view(), name='envelope_send'),
    path('<uuid:pk>/reject/', views.EnvelopeRejectView.as_view(), name='envelope_reject'),
    path('<uuid:pk>/edit/', views.EnvelopeEditView.as_view(), name='envelope_edit'),
    path('<uuid:pk>/delete/', views.EnvelopeDeleteView.as_view(), name='envelope_delete'),
]
