"""
Document model for the E-Sign application.

This module defines the Document model that represents uploaded documents
in the e-signature workflow.
"""

import uuid
from django.db import models
from django.conf import settings


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
        max_length=500,
        help_text="File path or S3 URL where the document is stored"
    )
    
    file_name = models.CharField(
        max_length=255,
        help_text="Original name of the uploaded file"
    )
    
    file_size = models.IntegerField(
        help_text="Size of the file in bytes"
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
    
    def __str__(self):
        return f"{self.file_name} ({self.status})"
    
    @property
    def file_size_mb(self):
        """Return file size in megabytes."""
        return round(self.file_size / (1024 * 1024), 2)