"""
Signature models for the E-Sign application.

This module defines the Signature model that represents individual
signatures within an envelope's signing workflow.
"""

import uuid
from django.db import models
from django.conf import settings


class Signature(models.Model):
    """
    Model representing a signature within an envelope's signing workflow.
    
    Each signature belongs to an envelope and tracks the signing status
    of individual signers in the sequential signing process.
    """
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("signed", "Signed"),
        ("declined", "Declined"),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the signature."
    )
    
    envelope = models.ForeignKey(
        'envelopes.Envelope',
        on_delete=models.CASCADE,
        related_name="signatures",
        help_text="The envelope this signature belongs to."
    )
    
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signatures",
        help_text="The user who needs to sign this document."
    )
    
    signature_image = models.TextField(
        blank=True,
        null=True,
        help_text="Base64 encoded signature image or signature data."
    )
    
    signed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the signature was completed."
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current status of the signature."
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the signature record was created."
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the signature record was last updated."
    )
    
    class Meta:
        ordering = ["created_at"]
        verbose_name = "Signature"
        verbose_name_plural = "Signatures"
        # Ensure one signature per signer per envelope
        unique_together = [['envelope', 'signer']]
        indexes = [
            models.Index(fields=['envelope', 'status']),
            models.Index(fields=['signer', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self) -> str:
        return f"Signature for {self.signer.email} in {self.envelope}"
    
    @property
    def is_signed(self) -> bool:
        """Returns True if the signature status is 'signed'."""
        return self.status == 'signed'
    
    @property
    def is_declined(self) -> bool:
        """Returns True if the signature status is 'declined'."""
        return self.status == 'declined'
    
    @property
    def is_pending(self) -> bool:
        """Returns True if the signature status is 'pending'."""
        return self.status == 'pending'

    @property
    def is_processing(self) -> bool:
        """Returns True if the signature status is 'processing'."""
        return self.status == 'processing'
    
    def get_signing_order(self) -> int:
        """
        Get the signing order for this signature within the envelope.
        
        Returns:
            int: The order number (1-based) for this signer in the envelope's signing_order
        """
        if not self.envelope.signing_order:
            return 0
        
        # Prefer explicit 'order' field defined in signing_order
        for i, signer_entry in enumerate(self.envelope.signing_order, 1):
            # Convert both to strings for consistent comparison
            stored_signer_id = str(signer_entry.get('signer_id'))
            current_signer_id = str(self.signer.id)
            
            if current_signer_id == stored_signer_id:
                explicit_order = signer_entry.get('order')
                if isinstance(explicit_order, int) and explicit_order >= 1:
                    return explicit_order
                # Fallback to positional index if 'order' is missing/invalid
                return i
        
        return 0
    
    def is_current_signer(self) -> bool:
        """
        Check if this signer is the current signer (lowest pending order).
        
        Returns:
            bool: True if this is the current signer who can act
        """
        if self.is_processing:
            return True
        if not self.is_pending and not self.is_processing:
            return False
        
        # Get all pending signatures for this envelope, ordered by signing order
        pending_signatures = Signature.objects.filter(
            envelope=self.envelope,
            status='pending'
        ).select_related('signer')
        
        if not pending_signatures.exists():
            return False
        
        # Convert to list to avoid QuerySet iteration issues
        pending_signatures_list = list(pending_signatures)
        
        if not pending_signatures_list:
            # Current signer may be in processing state
            return self.is_processing
        
        # Find the signature with the lowest signing order
        current_signature = min(
            pending_signatures_list,
            key=lambda sig: sig.get_signing_order()
        )
        
        return self.id == current_signature.id


class SigningJob(models.Model):
    """
    Tracks async PDF signing work for a signer on an envelope.
    """

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    envelope = models.ForeignKey(
        'envelopes.Envelope',
        on_delete=models.CASCADE,
        related_name='signing_jobs',
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='signing_jobs',
    )
    signature = models.ForeignKey(
        'Signature',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='signing_jobs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    signing_version = models.PositiveIntegerField(default=1)
    signature_image_data = models.TextField(blank=True, default='')
    fallback_placement = models.JSONField(default=dict, blank=True)
    is_self_sign = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default='')
    attempt_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['envelope', 'signer', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"SigningJob {self.id} ({self.status})"


class UserSignature(models.Model):
    """
    Model representing a reusable signature for a user.
    
    Users can upload multiple signatures and set one as default.
    These signatures can be reused when signing documents.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the user signature."
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_signatures",
        help_text="The user who owns this signature."
    )
    
    image = models.ImageField(
        upload_to="user_signatures/",
        help_text="The signature image file."
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the user's default signature."
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the signature was created."
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Signature"
        verbose_name_plural = "User Signatures"
        # Ensure only one default signature per user
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True),
                name='unique_default_signature_per_user'
            )
        ]
        indexes = [
            models.Index(fields=['user', 'is_default']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self) -> str:
        return f"Signature for {self.user.email} ({'default' if self.is_default else 'custom'})"
    
    def save(self, *args, **kwargs):
        """
        Override save to ensure only one default signature per user.
        """
        if self.is_default:
            # Set all other signatures for this user to non-default
            UserSignature.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
        
        super().save(*args, **kwargs)