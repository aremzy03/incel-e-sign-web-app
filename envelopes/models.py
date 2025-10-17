import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone # Import timezone for default name

class Envelope(models.Model):
    """
    Represents an envelope containing multiple documents for a signing workflow.

    An envelope manages the signing process for multiple documents, including
    the order of signers and the current status of the signing workflow.
    
    Each entry in signing_order defines a signer and their overall order in the envelope.
    Document-specific signature positions are managed in the EnvelopeDocument intermediary model.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the envelope."
    )

    # documents = models.ManyToManyField( # Removed to be replaced by ManyToManyField
    #     'documents.Document',
    #     through='EnvelopeDocument',
    #     related_name="envelopes",
    #     help_text="The documents that this envelope contains for signing."
    # )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_envelopes",
        help_text="The user who created this envelope."
    )

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="User-defined name of the envelope. Defaults to 'Untitled Envelope' + timestamp."
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
        help_text="List of signers in order: [{'signer_id': 'uuid', 'order': 1}, ...]. Document-specific positions are in EnvelopeDocument."
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
            models.Index(fields=['name']),
        ]

    def __str__(self) -> str:
        return f"Envelope: {self.name or self.id} ({self.status})"
    
    def clean(self):
        super().clean()
        if not self.name:
            self.name = f"Untitled Envelope - {timezone.now().strftime('%Y-%m-%d %H:%M')}"

        # Basic validation for signing_order (more detailed validation is in serializers)
        if not isinstance(self.signing_order, list):
            raise ValidationError({'signing_order': 'Signing order must be a list.'})

        signer_ids = set()
        orders = []

        for i, entry in enumerate(self.signing_order):
            if not isinstance(entry, dict):
                raise ValidationError({'signing_order': f'Entry {i} must be a dictionary.'})
            if 'signer_id' not in entry or 'order' not in entry:
                raise ValidationError({'signing_order': f'Entry {i} must have both "signer_id" and "order" keys.'})
            # Basic type checking for signer_id and order
            signer_id = str(entry['signer_id'])
            order = entry['order']

            try:
                uuid.UUID(signer_id)
            except ValueError:
                raise ValidationError({'signing_order': f'Entry {i}: signer_id must be a valid UUID.'})

            if not isinstance(order, int) or order < 1:
                raise ValidationError({'signing_order': f'Entry {i}: order must be a positive integer.'})
            
            # Detailed validation for duplicates and sequence
            if signer_id in signer_ids:
                raise ValidationError({'signing_order': f'Duplicate signer_id found: {signer_id}'})
            signer_ids.add(signer_id)

            if order in orders:
                raise ValidationError({'signing_order': f'Duplicate order found: {order}'})
            orders.append(order)
        
        # Validate order sequence (must start from 1, no gaps)
        if orders:
            orders.sort()
            expected_orders = list(range(1, len(orders) + 1))
            if orders != expected_orders:
                raise ValidationError({'signing_order': 'Orders must start from 1 and have no gaps.'})

        # Validate that all signer_ids correspond to existing users
        # This check should always run, even if during test migrations, unless explicitly disabled
        if signer_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            existing_user_ids = set(str(user_id) for user_id in 
                                    User.objects.filter(id__in=[uuid.UUID(s_id) for s_id in signer_ids]).values_list('id', flat=True))
            missing_user_ids = signer_ids - existing_user_ids
            if missing_user_ids:
                raise ValidationError({'signing_order': f'Users not found: {list(missing_user_ids)}'})

    def save(self, *args, **kwargs):
        """Override save to call clean() validation and handle default name."""
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
        """Returns True if the envelope status is 'pending'."""
        return self.status == 'pending'


class EnvelopeDocument(models.Model):
    """
    Intermediary model to manage the Many-to-Many relationship between Envelope and Document.
    Also stores document-specific signature positions for each signer within this envelope.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the EnvelopeDocument link."
    )

    envelope = models.ForeignKey(
        'Envelope',
        on_delete=models.CASCADE,
        related_name='envelopedocument_set',
        help_text="The envelope this document belongs to."
    )

    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='envelopedocument_set',
        help_text="The document included in this envelope."
    )

    order = models.IntegerField(
        help_text="The order of this document within the envelope (1-based)."
    )

    signer_document_positions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of signer positions for this document: [{'signer_id': 'uuid', 'position': {'page': 1, 'x': 100, 'y': 100, 'width': 120, 'height': 40}}, ...]"
    )

    class Meta:
        ordering = ['order']
        unique_together = [['envelope', 'document'], ['envelope', 'order']]
        verbose_name = "Envelope Document"
        verbose_name_plural = "Envelope Documents"
        indexes = [
            models.Index(fields=['envelope', 'order']),
            models.Index(fields=['document']),
        ]

    def __str__(self):
        return f"{self.order}. {self.document.file_name} in {self.envelope.name or self.envelope.id}"

    def clean(self):
        super().clean()
        if not isinstance(self.signer_document_positions, list):
            raise ValidationError({'signer_document_positions': 'Signer document positions must be a list.'})
        
        # Get signer IDs from the parent envelope's signing_order for validation
        envelope_signer_ids = set(str(s['signer_id']) for s in self.envelope.signing_order)

        for i, entry in enumerate(self.signer_document_positions):
            if not isinstance(entry, dict):
                raise ValidationError({'signer_document_positions': f'Entry {i} must be a dictionary.'})
            
            if 'signer_id' not in entry:
                raise ValidationError({'signer_document_positions': f'Entry {i} must have "signer_id" key.'})
            if 'position' not in entry:
                raise ValidationError({'signer_document_positions': f'Entry {i} must have "position" key.'})

            signer_id = str(entry['signer_id'])
            position = entry['position']

            # Validate signer_id is a valid UUID and exists in the parent envelope's signing_order
            try:
                uuid.UUID(signer_id)
                if signer_id not in envelope_signer_ids:
                    raise ValidationError({'signer_document_positions': f'Signer ID {signer_id} not found in Envelope signing_order.'})
            except ValueError:
                raise ValidationError({'signer_document_positions': f'Entry {i}: signer_id must be a valid UUID.'})

            if not isinstance(position, dict):
                raise ValidationError({'signer_document_positions': f'Entry {i}: position must be a dict.'})
            
            required_position_keys = ["page", "x", "y", "width", "height"]
            for key in required_position_keys:
                if key not in position:
                    raise ValidationError({'signer_document_positions': f'Entry {i}: position must include {key}.'})
                
                value = position[key]
                # Changed to allow 0 for position values (x, y, width, height) but page must be >= 1
                if not isinstance(value, (int, float)) or (key == "page" and value < 1) or (key != "page" and value < 0):
                    raise ValidationError({'signer_document_positions': f'Entry {i}: position[{key}] must be a positive number or zero (page must be >= 1).'})