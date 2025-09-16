"""
URL patterns for notifications in the E-Sign application.
"""

from django.urls import path
from .views import NotificationListView, NotificationReadView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('<uuid:notification_id>/read/', NotificationReadView.as_view(), name='notification-read'),
]
