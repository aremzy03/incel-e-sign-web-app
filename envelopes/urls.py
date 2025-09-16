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
    path('<uuid:pk>/', views.EnvelopeDetailView.as_view(), name='envelope_detail'),
    path('create/', views.EnvelopeCreateView.as_view(), name='envelope_create'),
    path('<uuid:pk>/send/', views.EnvelopeSendView.as_view(), name='envelope_send'),
    path('<uuid:pk>/reject/', views.EnvelopeRejectView.as_view(), name='envelope_reject'),
]
