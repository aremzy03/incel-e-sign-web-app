"""
Serializers for the signatures app.

This module defines serializers for signature-related operations
in the e-signature workflow.
"""

from rest_framework import serializers
from .models import Signature, UserSignature
from django.core.files.base import ContentFile
from PIL import Image
from io import BytesIO
import logging


logger = logging.getLogger(__name__)


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
    
    # Placement fields (optional fallbacks; position data primarily comes from envelope's signing_order)
    page = serializers.IntegerField(required=False, min_value=1, help_text="1-based page number (fallback if not defined in envelope)")
    x = serializers.FloatField(required=False, help_text="X coordinate in points from left edge (fallback if not defined in envelope)")
    y = serializers.FloatField(required=False, help_text="Y coordinate in points from top edge - UI convention (fallback if not defined in envelope)")
    width = serializers.FloatField(required=False, min_value=1, help_text="Signature width in points (fallback if not defined in envelope)")
    height = serializers.FloatField(required=False, min_value=1, help_text="Signature height in points (fallback if not defined in envelope)")
    
    def validate(self, data):
        """
        Validate signature data. Either signature_image, signature_id, or default signature is used.
        Position coordinates are optional since they primarily come from envelope's signing_order.
        
        Args:
            data: Dictionary containing the validated data
            
        Returns:
            dict: Validated data
            
        Raises:
            ValidationError: If both signature_image and signature_id are provided
        """
        signature_image = data.get('signature_image')
        signature_id = data.get('signature_id')
        
        # Note: It's valid to provide neither - the system will try to use default signature
        # The actual validation for signature availability happens in the view
        
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

    def to_internal_value(self, data):
        # Apply defaults for placement if not provided
        obj = super().to_internal_value(data)
        obj.setdefault('page', 1)
        obj.setdefault('x', 100.0)
        obj.setdefault('y', 100.0)
        obj.setdefault('width', 120.0)
        obj.setdefault('height', 40.0)
        return obj


class DeclineSignatureSerializer(serializers.Serializer):
    """
    Serializer for declining a signature.
    
    Accepts an optional decline message.
    """
    
    decline_message = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional message/reason for declining the signature."
    )


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

    def _remove_background(self, image_field):
        """
        Run the uploaded image through rembg (if available) and then apply a
        white/near-white background to transparent alpha mask.

        Args:
            image_field: Uploaded image file (InMemoryUploadedFile or similar)

        Returns:
            ContentFile or None: Processed PNG image with transparent background,
            or None if processing is not available or fails.
        """
        # Read original bytes
        original_bytes = image_field.read()
        # Reset pointer so the original file can still be used if needed
        image_field.seek(0)

        processed_bytes = original_bytes

        # First, try rembg if available
        try:
            from rembg import remove  # type: ignore

            try:
                processed_bytes = remove(original_bytes)
            except (Exception, SystemExit) as exc:  # SystemExit raised when model download fails
                logger.error("rembg background removal failed: %s", exc, exc_info=True)
                processed_bytes = original_bytes
        except (Exception, SystemExit) as exc:  # pragma: no cover - environment-specific
            logger.warning("rembg is not available; falling back to simple background removal: %s", exc)
            processed_bytes = original_bytes

        # Now enforce transparency for white / near-white pixels using Pillow
        try:
            img = Image.open(BytesIO(processed_bytes)).convert("RGBA")
            datas = img.getdata()

            new_data = []
            # Threshold for what counts as "white / near-white"
            threshold = 240
            for r, g, b, a in datas:
                if r >= threshold and g >= threshold and b >= threshold:
                    # Make near-white fully transparent
                    new_data.append((r, g, b, 0))
                else:
                    new_data.append((r, g, b, a))

            img.putdata(new_data)

            output = BytesIO()
            img.save(output, format="PNG")
            processed_bytes = output.getvalue()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Pillow background post-processing failed: %s", exc, exc_info=True)
            # If Pillow fails, fall back to whatever we had
            pass

        # Ensure PNG filename
        original_name = getattr(image_field, "name", "signature.png")
        if not original_name.lower().endswith(".png"):
            original_name = "signature.png"

        return ContentFile(processed_bytes, name=original_name)
    
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

        # Apply background removal if an image is provided
        image = validated_data.get("image")
        if image is not None:
            processed = self._remove_background(image)
            if processed is not None:
                validated_data["image"] = processed

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
        image = validated_data.get("image")
        if image is not None:
            processed = self._remove_background(image)
            if processed is not None:
                validated_data["image"] = processed

        return super().update(instance, validated_data)
