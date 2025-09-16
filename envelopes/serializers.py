"""
Serializers for the envelopes app.

This module defines serializers for envelope-related operations
in the e-signature workflow.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Envelope
from documents.models import Document

User = get_user_model()


class EnvelopeCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new envelopes.
    
    Validates document ownership and signing order before creating
    an envelope with status="draft".
    """
    
    document_id = serializers.UUIDField(
        write_only=True,
        help_text="UUID of the document to create envelope for"
    )
    
    signing_order = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True,
        help_text="List of signers in order: [{'signer_id': 'uuid', 'order': 1}, ...]"
    )
    
    class Meta:
        model = Envelope
        fields = ['document_id', 'signing_order']
    
    def validate_document_id(self, value):
        """
        Validate that the document exists and belongs to the request user.
        """
        try:
            document = Document.objects.get(id=value)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document not found.")
        
        # Check if document belongs to the request user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            if document.owner != request.user:
                raise serializers.ValidationError(
                    "You can only create envelopes for your own documents."
                )
        
        return value
    
    def validate_signing_order(self, value):
        """
        Validate the signing order structure and content.
        
        Ensures:
        - Each entry has 'signer_id' and 'order' keys
        - Orders start at 1 and are unique (no duplicates, no gaps)
        - All signer_ids reference valid users
        """
        if not isinstance(value, list):
            raise serializers.ValidationError("Signing order must be a list.")
        
        if not value:
            # Empty list is valid (no signers yet)
            return value
        
        # Validate each signer entry
        signer_ids = set()
        orders = []
        
        for i, signer_entry in enumerate(value):
            if not isinstance(signer_entry, dict):
                raise serializers.ValidationError(
                    f"Entry {i} must be a dictionary."
                )
            
            # Check required keys
            if 'signer_id' not in signer_entry or 'order' not in signer_entry:
                raise serializers.ValidationError(
                    f"Entry {i} must have both 'signer_id' and 'order' keys."
                )
            
            signer_id = signer_entry['signer_id']
            order = signer_entry['order']
            
            # Validate signer_id format (should be UUID string)
            try:
                signer_id_str = str(signer_id)
                # Try to convert to UUID to validate format
                import uuid
                uuid.UUID(signer_id_str)
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Entry {i}: signer_id must be a valid UUID."
                )
            
            # Validate order is a positive integer
            if not isinstance(order, int) or order < 1:
                raise serializers.ValidationError(
                    f"Entry {i}: order must be a positive integer."
                )
            
            # Check for duplicate signer_ids
            if signer_id in signer_ids:
                raise serializers.ValidationError(
                    f"Duplicate signer_id found: {signer_id}"
                )
            signer_ids.add(signer_id)
            
            # Check for duplicate orders
            if order in orders:
                raise serializers.ValidationError(
                    f"Duplicate order found: {order}"
                )
            orders.append(order)
        
        # Validate order sequence (must start from 1, no gaps)
        if orders:
            orders.sort()
            expected_orders = list(range(1, len(orders) + 1))
            if orders != expected_orders:
                raise serializers.ValidationError(
                    "Orders must start from 1 and have no gaps."
                )
        
        # Validate that all signer_ids correspond to existing users
        if signer_ids:
            # Convert string UUIDs to UUID objects for the database query
            import uuid
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
                raise serializers.ValidationError(
                    f"Users not found: {list(missing_user_ids)}"
                )
        
        return value
    
    def create(self, validated_data):
        """
        Create a new envelope with status="draft".
        
        Extracts document_id and signing_order from validated_data,
        creates the envelope, and stores signing_order as JSON.
        """
        document_id = validated_data.pop('document_id')
        signing_order = validated_data.pop('signing_order', [])
        
        # Get the document
        document = Document.objects.get(id=document_id)
        
        # Get the creator from the request context
        request = self.context.get('request')
        creator = request.user if request else None
        
        if not creator:
            raise serializers.ValidationError("User authentication required.")
        
        # Create the envelope
        envelope = Envelope.objects.create(
            document=document,
            creator=creator,
            status="draft",
            signing_order=signing_order
        )
        
        return envelope


class EnvelopeDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for envelope details (read-only).
    """
    
    document_file_name = serializers.CharField(
        source='document.file_name',
        read_only=True
    )
    
    creator_email = serializers.CharField(
        source='creator.email',
        read_only=True
    )
    
    signer_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Envelope
        fields = [
            'id', 'document', 'document_file_name', 'creator', 'creator_email',
            'status', 'signing_order', 'signer_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'document', 'creator', 'status', 'created_at', 'updated_at'
        ]


class SignatureSerializer(serializers.ModelSerializer):
    """
    Serializer for signature details (read-only).
    
    Used for nested serialization within envelope responses.
    """
    
    class Meta:
        model = None  # Will be set dynamically
        fields = ['signer', 'status', 'signed_at']
        read_only_fields = ['signer', 'status', 'signed_at']


class EnvelopeSerializer(serializers.ModelSerializer):
    """
    Serializer for envelope details (read-only).
    
    Used for returning envelope data in send/reject operations and retrieval.
    Includes nested signature information.
    """
    
    signatures = serializers.SerializerMethodField()
    
    class Meta:
        model = Envelope
        fields = [
            'id', 'document', 'creator', 'status', 'signing_order', 
            'created_at', 'updated_at', 'signatures'
        ]
        read_only_fields = [
            'id', 'document', 'creator', 'status', 'signing_order', 
            'created_at', 'updated_at', 'signatures'
        ]
    
    def get_signatures(self, obj):
        """
        Get signatures for this envelope with signer, status, and signed_at.
        """
        from signatures.models import Signature
        
        signatures = obj.signatures.all().order_by('created_at')
        signature_data = []
        
        for signature in signatures:
            signature_data.append({
                'signer': str(signature.signer.id),
                'status': signature.status,
                'signed_at': signature.signed_at.isoformat() if signature.signed_at else None
            })
        
        return signature_data
