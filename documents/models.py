"""
Document model for the E-Sign application.

This module defines the Document model that represents uploaded documents
in the e-signature workflow.
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Document(models.Model):
    """
    Model representing a document in the e-signature workflow.
    
    Each document belongs to a user (owner) and tracks its status
    through the signing process.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the document"
    )
    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text="User who owns this document"
    )
    
    file_url = models.CharField(
        max_length=2048,
        help_text="File path or S3 URL where the document is stored"
    )
    
    file_name = models.CharField(
        max_length=255,
        help_text="Original name of the uploaded file"
    )
    
    file_size = models.IntegerField(
        help_text="Size of the file in bytes"
    )
    
    signed_file_url = models.CharField(
        max_length=2048,
        blank=True,
        null=True,
        help_text="File path or URL to the signed PDF version if available"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current status of the document in the signing workflow"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the document was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the document was last updated"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.file_name} ({self.status})"

    def clean(self):
        super().clean()
        if not self.file_url or not self.file_url.strip():
            raise ValidationError({"file_url": "Document file_url cannot be blank."})

    def save(self, *args, **kwargs):
        skip_validation = kwargs.pop("skip_validation", False)
        if not skip_validation:
            self.full_clean()
        return super().save(*args, **kwargs)
    
    @property
    def file_size_mb(self):
        """Return file size in megabytes."""
        return round(self.file_size / (1024 * 1024), 2)


class DocumentEditSession(models.Model):
    """
    Unsaved additive-text operations for one owner and one document file.

    The PDF is not modified until commit. ops is replaced wholesale on autosave.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        COMMITTED = "committed", "Committed"
        DISCARDED = "discarded", "Discarded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        related_name="edit_sessions",
        on_delete=models.CASCADE,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_edit_sessions",
    )
    base_file_url = models.CharField(max_length=2048)
    ops = models.JSONField(default=list)
    page_meta = models.JSONField(
        default=list,
        help_text="Page sizes captured when the session was opened.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "status"]),
            models.Index(fields=["document", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Text edit {self.status} on {self.document_id}"


class DocumentRevision(models.Model):
    """A stored PDF object that Document.file_url has pointed at."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        related_name="revisions",
        on_delete=models.CASCADE,
    )
    file_url = models.CharField(max_length=2048)
    file_size = models.IntegerField()
    source = models.CharField(max_length=32)
    session = models.ForeignKey(
        DocumentEditSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Revision {self.source} of {self.document_id}"
