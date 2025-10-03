"""
API views for contacts management and recipient search/invite.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Contact
from .serializers import ContactSerializer, ContactSearchSerializer

User = get_user_model()


class ContactListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contacts = Contact.objects.filter(owner=request.user).order_by("-created_at")
        data = ContactSerializer(contacts, many=True).data
        return Response({
            "success": True,
            "message": "Contacts retrieved successfully",
            "data": data,
        }, status=status.HTTP_200_OK)


class ContactSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ContactSearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        try:
            user = User.objects.get(email__iexact=email)
            return Response({
                "success": True,
                "message": "User exists",
                "data": {
                    "exists": True,
                    "user": {
                        "id": str(user.id),
                        "email": user.email,
                        "full_name": user.full_name,
                    }
                }
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({
                "success": True,
                "message": "User not found. You can invite them.",
                "data": {
                    "exists": False,
                    "invite": True,
                    "email": email,
                }
            }, status=status.HTTP_200_OK)


class ContactAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        name = request.data.get("name", "").strip()
        if not email:
            return Response({
                "success": False,
                "message": "Validation failed",
                "data": {"email": ["This field is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        contact_user = None
        try:
            contact_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            contact_user = None

        # Auto-populate name from user's full_name if user exists and name not provided
        if contact_user and not name:
            name = contact_user.full_name

        try:
            contact, _created = Contact.objects.get_or_create(
                owner=request.user,
                email=email,
                defaults={
                    "name": name,
                    "contact_user": contact_user,
                }
            )
            # If exists, update name/contact_user if changed
            updated = False
            if name and contact.name != name:
                contact.name = name
                updated = True
            if contact_user and contact.contact_user_id != contact_user.id:
                contact.contact_user = contact_user
                updated = True
            if updated:
                contact.save()
        except IntegrityError:
            return Response({
                "success": False,
                "message": "A contact with this email already exists.",
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "Contact saved successfully",
            "data": ContactSerializer(contact).data
        }, status=status.HTTP_201_CREATED)


class ContactInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from notifications.utils import send_invite_email

        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response({
                "success": False,
                "message": "Validation failed",
                "data": {"email": ["This field is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save or update contact as invited
        contact_user = None
        try:
            contact_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            contact_user = None

        # Determine name default if user exists
        name = request.data.get("name", "").strip()
        if contact_user and not name:
            name = contact_user.full_name

        contact, _ = Contact.objects.get_or_create(
            owner=request.user,
            email=email,
            defaults={
                "name": name,
                "contact_user": contact_user,
            },
        )
        if contact_user and contact.contact_user_id != contact_user.id:
            contact.contact_user = contact_user
            # If name is empty on existing contact, fill from user full_name
            if not contact.name and contact_user.full_name:
                contact.name = contact_user.full_name
            contact.save()

        # Send invite email via Celery helper
        try:
            send_invite_email(email, request.user)
        except Exception:
            # Ensure API still succeeds; background system may be unavailable
            pass

        return Response({
            "success": True,
            "message": "Invitation sent (if user not registered).",
            "data": ContactSerializer(contact).data
        }, status=status.HTTP_200_OK)


class ContactDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        contact = get_object_or_404(Contact, pk=pk, owner=request.user)
        contact.delete()
        return Response({
            "success": True,
            "message": "Contact deleted successfully",
        }, status=status.HTTP_204_NO_CONTENT)


# Create your views here.
