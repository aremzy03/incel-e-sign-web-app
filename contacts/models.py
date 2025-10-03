"""
Database models for the contacts app.

Provides the Contact model for saving frequently used recipients
and tracking whether a contact is a registered user or invited-only.
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Contact(models.Model):
    """
    Contact saved by a user for quick recipient selection.

    - Unique per (owner, email)
    - Optionally linked to a registered user via contact_user
    - Stores email and optional display name
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    contact_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="as_contact",
    )
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        unique_together = ("owner", "email")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.owner_id})"

# Create your models here.
