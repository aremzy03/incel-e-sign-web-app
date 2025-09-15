"""
URL configuration for the documents app.

This module defines URL patterns for document-related endpoints
in the e-signature workflow.
"""

from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('', views.DocumentListView.as_view(), name='document_list'),
    path('<uuid:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('<uuid:pk>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),
]
