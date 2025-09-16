"""
Views for notifications in the E-Sign application.
"""

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(ListAPIView):
    """
    List all notifications for the authenticated user.
    
    GET /notifications/
    - Returns notifications ordered by created_at desc
    - Only shows notifications for the current user
    """
    
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return notifications for the current user only."""
        return Notification.objects.filter(user=self.request.user)


class NotificationReadView(APIView):
    """
    Mark a notification as read for the authenticated user.
    
    PATCH /notifications/{id}/read/
    - Marks the specified notification as read
    - Only allows users to mark their own notifications as read
    """
    
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, notification_id):
        """Mark the notification as read."""
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            user=request.user
        )
        
        notification.is_read = True
        notification.save()
        
        serializer = NotificationSerializer(notification)
        return Response({
            "success": True,
            "message": "Notification marked as read",
            "data": serializer.data
        }, status=status.HTTP_200_OK)