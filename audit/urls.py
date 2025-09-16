"""
URL routing for audit logging API endpoints.
"""

from django.urls import path
from .views import AuditLogListView, AuditLogDetailView

app_name = 'audit'

urlpatterns = [
    path("logs/", AuditLogListView.as_view(), name="audit-log-list"),
    path("logs/<uuid:pk>/", AuditLogDetailView.as_view(), name="audit-log-detail"),
]
