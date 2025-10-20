"""
Serializers for the contacts app.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Contact

User = get_user_model()


class ContactSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    contact_user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Contact
        fields = ["id", "email", "name", "contact_user_id", "status", "created_at"]

    def get_status(self, obj: Contact) -> str:
        return "registered" if obj.contact_user_id else "invited"


class ContactSearchSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


