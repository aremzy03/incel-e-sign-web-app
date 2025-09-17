"""
Serializers for the signatures app.

This module defines serializers for signature-related operations
in the e-signature workflow.
"""

from rest_framework import serializers
from .models import Signature, UserSignature


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
    
    Accepts either signature_image (base64 encoded signature data) or signature_id (UUID of UserSignature).
    """
    
    signature_image = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Base64 encoded signature image or signature data."
    )
    
    signature_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID of a UserSignature to use for signing."
    )
    
    def validate(self, data):
        """
        Validate that either signature_image or signature_id is provided.
        
        Args:
            data: Dictionary containing the validated data
            
        Returns:
            dict: Validated data
            
        Raises:
            ValidationError: If neither signature_image nor signature_id is provided
        """
        signature_image = data.get('signature_image')
        signature_id = data.get('signature_id')
        
        if not signature_image and not signature_id:
            raise serializers.ValidationError(
                "Either signature_image or signature_id must be provided."
            )
        
        if signature_image and signature_id:
            raise serializers.ValidationError(
                "Provide either signature_image or signature_id, not both."
            )
        
        return data
    
    def validate_signature_image(self, value):
        """
        Validate the signature image data.
        
        Args:
            value: Base64 encoded signature data or data URL
            
        Returns:
            str: Validated signature data
        """
        if not value or not value.strip():
            return value  # Allow empty since signature_id might be provided
        
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
    
    def validate_signature_id(self, value):
        """
        Validate the signature_id field.
        
        Args:
            value: UUID of the UserSignature
            
        Returns:
            UUID: Validated UUID
        """
        if value:
            # Check if the UserSignature exists and belongs to the current user
            request = self.context.get('request')
            if request and hasattr(request, 'user'):
                try:
                    user_signature = UserSignature.objects.get(
                        id=value,
                        user=request.user
                    )
                except UserSignature.DoesNotExist:
                    raise serializers.ValidationError(
                        "UserSignature not found or does not belong to you."
                    )
        
        return value


class DeclineSignatureSerializer(serializers.Serializer):
    """
    Serializer for declining a signature.
    
    No additional fields required - just the action.
    """
    
    # No fields needed - this is just an action serializer
    pass


class UserSignatureSerializer(serializers.ModelSerializer):
    """
    Serializer for user signature CRUD operations.
    
    Handles file upload validation and default signature management.
    """
    
    class Meta:
        model = UserSignature
        fields = ['id', 'image', 'is_default', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate_image(self, value):
        """
        Validate the uploaded signature image.
        
        Args:
            value: Uploaded image file
            
        Returns:
            File: Validated image file
            
        Raises:
            ValidationError: If file size exceeds 1MB or invalid format
        """
        if not value:
            raise serializers.ValidationError("Signature image is required.")
        
        # Check file size (1MB = 1024 * 1024 bytes)
        max_size = 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size must not exceed 1MB. Current size: {value.size} bytes."
            )
        
        # Check file format (allow common image formats)
        allowed_formats = ['JPEG', 'JPG', 'PNG', 'GIF', 'BMP', 'WEBP']
        if value.image.format not in allowed_formats:
            raise serializers.ValidationError(
                f"Unsupported file format. Allowed formats: {', '.join(allowed_formats)}"
            )
        
        return value
    
    def validate_is_default(self, value):
        """
        Validate the is_default field.
        
        Args:
            value: Boolean indicating if this should be the default signature
            
        Returns:
            bool: Validated boolean value
        """
        if value and hasattr(self, 'instance') and self.instance:
            # If updating an existing signature to be default
            user = self.instance.user
        elif hasattr(self, 'initial_data') and 'user' in self.initial_data:
            # If creating a new signature
            user = self.initial_data['user']
        else:
            # This will be set in the view
            return value
        
        # Check if user already has a default signature
        if value:
            existing_default = UserSignature.objects.filter(
                user=user,
                is_default=True
            ).exclude(id=getattr(self.instance, 'id', None))
            
            if existing_default.exists():
                # This will be handled by the model's save method
                pass
        
        return value
    
    def create(self, validated_data):
        """
        Create a new user signature.
        
        Args:
            validated_data: Validated data for creating the signature
            
        Returns:
            UserSignature: Created signature instance
        """
        # Set the user from the request context
        user = self.context['request'].user
        validated_data['user'] = user
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """
        Update an existing user signature.
        
        Args:
            instance: Existing UserSignature instance
            validated_data: Validated data for updating
            
        Returns:
            UserSignature: Updated signature instance
        """
        return super().update(instance, validated_data)
