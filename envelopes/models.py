import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings


class Envelope(models.Model):
    """
    Represents an envelope containing a document for signing workflow.
    
    An envelope manages the signing process for a document, including
    the order of signers and the current status of the signing workflow.
    """
    
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the envelope."
    )
    
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name="envelopes",
        help_text="The document that this envelope contains for signing."
    )
    
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_envelopes",
        help_text="The user who created this envelope."
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        help_text="Current status of the envelope in the signing workflow."
    )
    
    signing_order = models.JSONField(
        default=list,
        blank=True,
        help_text="List of signers in order: [{'signer_id': 'uuid', 'order': 1}, ...]"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the envelope was created."
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the envelope was last updated."
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Envelope"
        verbose_name_plural = "Envelopes"
        indexes = [
            models.Index(fields=['creator', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self) -> str:
        return f"Envelope for {self.document.file_name} ({self.status})"
    
    def clean(self):
        """
        Validate the signing_order field.
        
        Ensures:
        - signing_order is a list of dictionaries
        - Each dict has 'signer_id' and 'order' keys
        - Orders start from 1 and are unique (no duplicates, no gaps)
        - signer_id values correspond to existing users
        """
        super().clean()
        
        if not isinstance(self.signing_order, list):
            raise ValidationError({
                'signing_order': 'Signing order must be a list.'
            })
        
        if not self.signing_order:
            # Empty list is valid (no signers yet)
            return
        
        # Validate each signer entry
        signer_ids = set()
        orders = []
        
        for i, signer_entry in enumerate(self.signing_order):
            if not isinstance(signer_entry, dict):
                raise ValidationError({
                    'signing_order': f'Entry {i} must be a dictionary.'
                })
            
            # Check required keys
            if 'signer_id' not in signer_entry or 'order' not in signer_entry:
                raise ValidationError({
                    'signing_order': f'Entry {i} must have both "signer_id" and "order" keys.'
                })
            
            signer_id = signer_entry['signer_id']
            order = signer_entry['order']
            
            # Validate signer_id format (should be UUID string)
            try:
                # Convert to string first, then validate UUID
                signer_id_str = str(signer_id)
                uuid.UUID(signer_id_str)
            except (ValueError, TypeError):
                raise ValidationError({
                    'signing_order': f'Entry {i}: signer_id must be a valid UUID.'
                })
            
            # Validate order is a positive integer
            if not isinstance(order, int) or order < 1:
                raise ValidationError({
                    'signing_order': f'Entry {i}: order must be a positive integer.'
                })
            
            # Check for duplicate signer_ids
            if signer_id in signer_ids:
                raise ValidationError({
                    'signing_order': f'Duplicate signer_id found: {signer_id}'
                })
            signer_ids.add(signer_id)
            
            # Check for duplicate orders
            if order in orders:
                raise ValidationError({
                    'signing_order': f'Duplicate order found: {order}'
                })
            orders.append(order)
        
        # Validate order sequence (must start from 1, no gaps)
        if orders:
            orders.sort()
            expected_orders = list(range(1, len(orders) + 1))
            if orders != expected_orders:
                raise ValidationError({
                    'signing_order': 'Orders must start from 1 and have no gaps.'
                })
        
        # Validate that all signer_ids correspond to existing users
        # Only check if we have signers and we're not in a migration
        if signer_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # Convert string UUIDs back to UUID objects for the database query
            uuid_signers = []
            for signer_id in signer_ids:
                try:
                    uuid_signers.append(uuid.UUID(signer_id))
                except (ValueError, TypeError):
                    # This should have been caught earlier, but just in case
                    continue
            
            existing_user_ids = set(
                str(user_id) for user_id in 
                User.objects.filter(id__in=uuid_signers).values_list('id', flat=True)
            )
            missing_user_ids = signer_ids - existing_user_ids
            if missing_user_ids:
                raise ValidationError({
                    'signing_order': f'Users not found: {list(missing_user_ids)}'
                })
    
    def save(self, *args, **kwargs):
        """Override save to call clean() validation."""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def signer_count(self) -> int:
        """Returns the number of signers in the signing order."""
        return len(self.signing_order)
    
    @property
    def is_completed(self) -> bool:
        """Returns True if the envelope status is 'completed'."""
        return self.status == 'completed'
    
    @property
    def is_sent(self) -> bool:
        """Returns True if the envelope status is 'sent'."""
        return self.status == 'sent'