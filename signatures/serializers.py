"""
Serializers for the signatures app.

This module defines serializers for signature-related operations
in the e-signature workflow.
"""

from rest_framework import serializers
from .models import Signature


class SignatureSerializer(serializers.ModelSerializer):
    """
    Serializer for signature details (read-only).
    
    Used for returning signature data in API responses.
    """
    
    signer_email = serializers.CharField(
        source='signer.email',
        read_only=True
    )
    
    signer_name = serializers.CharField(
        source='signer.full_name',
        read_only=True
    )
    
    signing_order = serializers.SerializerMethodField()
    
    class Meta:
        model = Signature
        fields = [
            'id', 'signer', 'signer_email', 'signer_name', 'status', 
            'signing_order', 'signed_at', 'signature_image', 
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'signer', 'status', 'signed_at', 'signature_image',
            'created_at', 'updated_at'
        ]
    
    def get_signing_order(self, obj):
        """Get the signing order for this signature."""
        return obj.get_signing_order()


class SignDocumentSerializer(serializers.Serializer):
    """
    Serializer for signing a document.
    
    Accepts signature_image (base64 encoded signature data).
    """
    
    signature_image = serializers.CharField(
        required=True,
        help_text="Base64 encoded signature image or signature data."
    )
    
    def validate_signature_image(self, value):
        """
        Validate the signature image data.
        
        Args:
            value: Base64 encoded signature data or data URL
            
        Returns:
            str: Validated signature data
        """
        if not value or not value.strip():
            raise serializers.ValidationError("Signature image is required.")
        
        # Handle data URLs (data:image/png;base64,<data>)
        if value.startswith('data:'):
            if ';base64,' in value:
                # Extract the base64 part after the comma
                base64_data = value.split(';base64,', 1)[1]
            else:
                raise serializers.ValidationError(
                    "Data URL must contain base64 encoded data."
                )
        else:
            # Assume it's raw base64 data
            base64_data = value
        
        # Basic validation - check if it looks like base64
        import base64
        try:
            # Try to decode to validate base64 format
            base64.b64decode(base64_data, validate=True)
        except Exception:
            raise serializers.ValidationError(
                "Signature image must be valid base64 encoded data."
            )
        
        return value.strip()


class DeclineSignatureSerializer(serializers.Serializer):
    """
    Serializer for declining a signature.
    
    No additional fields required - just the action.
    """
    
    # No fields needed - this is just an action serializer
    pass
