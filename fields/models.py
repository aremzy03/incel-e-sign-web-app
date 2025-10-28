"""
Models for the fields app.

Defines non-signature annotation fields (initials, date, text, designation)
that can be prefilled by the sender or filled by assigned signers.
"""

import uuid
from django.db import models
from django.conf import settings


class Field(models.Model):
    """
    Represents a non-signature field placed on a document within an envelope.

    Coordinates are stored in PDF points using a top-left origin convention for Y.
    """

    class FieldType(models.TextChoices):
        SIGNATURE = "signature", "Signature"
        INITIALS = "initials", "Initials"
        DATE = "date", "Date"
        TEXT = "text", "Text"
        DESIGNATION = "designation", "Designation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    envelope = models.ForeignKey(
        'envelopes.Envelope', on_delete=models.CASCADE, related_name='fields', help_text="Envelope this field belongs to."
    )
    document = models.ForeignKey(
        'documents.Document', on_delete=models.CASCADE, related_name='fields', help_text="Document this field is placed on."
    )

    page = models.IntegerField(help_text="1-based page number.")
    x = models.FloatField(help_text="X coordinate in points from left edge.")
    y = models.FloatField(help_text="Y coordinate in points from top edge (UI convention).")
    width = models.FloatField(help_text="Width in points.")
    height = models.FloatField(help_text="Height in points.")

    type = models.CharField(max_length=20, choices=FieldType.choices)

    assigned_signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_fields',
        help_text="Signer assigned to fill this field."
    )

    required = models.BooleanField(default=False, help_text="Whether the field must be filled by the signer.")

    prefill_value = models.TextField(null=True, blank=True, help_text="Value prefilled by the sender.")
    value = models.TextField(null=True, blank=True, help_text="Value provided by the signer during signing.")
    placeholder = models.CharField(max_length=255, null=True, blank=True)

    font_family = models.CharField(max_length=255, null=True, blank=True, help_text="ReportLab font name or path to TTF.")
    font_size = models.FloatField(null=True, blank=True)
    date_format = models.CharField(max_length=32, null=True, blank=True, help_text="Display format for date fields.")
    max_length = models.IntegerField(null=True, blank=True, help_text="Max length for text/designation.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['envelope', 'document']),
            models.Index(fields=['document', 'page']),
            models.Index(fields=['assigned_signer']),
        ]

    def __str__(self) -> str:
        return f"Field {self.type} on p{self.page} of {self.document_id}"

