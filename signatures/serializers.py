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

from django.db import transaction
from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from fields.models import Field as FieldModel

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


class SelfSignPositionSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=True)
    x = serializers.FloatField(min_value=0.0, required=True)
    y = serializers.FloatField(min_value=0.0, required=True)
    width = serializers.FloatField(min_value=0.0, required=True)
    height = serializers.FloatField(min_value=0.0, required=True)


class SelfSignSignerDocumentPositionSerializer(serializers.Serializer):
    signer_id = serializers.UUIDField(required=False, allow_null=True)
    position = SelfSignPositionSerializer()


class SelfSignDocumentWithPositionsSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(required=True)
    signer_document_positions = serializers.ListField(
        child=SelfSignSignerDocumentPositionSerializer(),
        required=False,
        allow_empty=True,
    )


class SelfSignSerializer(serializers.Serializer):
    """
    Serializer for one-call self-sign envelope creation and signing.

    Composes envelope creation validation with sign payload validation.
    """

    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        help_text="List of UUIDs of the documents to include in the envelope.",
    )
    name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional user-defined name for the envelope.",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional description or notes for this envelope.",
    )
    documents_with_positions = serializers.ListField(
        child=SelfSignDocumentWithPositionsSerializer(),
        required=False,
        allow_empty=True,
        help_text="Optional document-specific signature positions.",
    )
    fields = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Optional non-signature fields with inline values.",
    )
    pdf_password_protection_enabled = serializers.BooleanField(required=False, default=True)
    signature_image = SignDocumentSerializer().fields['signature_image']
    signature_id = SignDocumentSerializer().fields['signature_id']
    page = SignDocumentSerializer().fields['page']
    x = SignDocumentSerializer().fields['x']
    y = SignDocumentSerializer().fields['y']
    width = SignDocumentSerializer().fields['width']
    height = SignDocumentSerializer().fields['height']

    def validate(self, attrs):
        from envelopes.serializers import EnvelopeCreateSerializer

        if 'signing_order' in self.initial_data:
            raise serializers.ValidationError({
                'signing_order': 'signing_order is not accepted for self-sign envelopes.',
            })

        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            raise serializers.ValidationError('User authentication required.')
        user = request.user

        documents_with_positions = attrs.get('documents_with_positions') or []
        normalized_documents_with_positions = []
        for entry in documents_with_positions:
            normalized_entry = {
                'document_id': entry['document_id'],
                'signer_document_positions': [],
            }
            for signer_pos in entry.get('signer_document_positions', []):
                signer_id = signer_pos.get('signer_id')
                if signer_id is not None and str(signer_id) != str(user.id):
                    raise serializers.ValidationError({
                        'documents_with_positions': (
                            f"Signer ID {signer_id} is not allowed in self-sign envelopes."
                        ),
                    })
                normalized_entry['signer_document_positions'].append({
                    'signer_id': user.id,
                    'position': signer_pos['position'],
                })
            normalized_documents_with_positions.append(normalized_entry)
        attrs['documents_with_positions'] = normalized_documents_with_positions

        fields_data = attrs.get('fields') or []
        normalized_fields = []
        for item in fields_data:
            normalized_item = dict(item)
            assigned_signer = normalized_item.get('assigned_signer')
            if assigned_signer is not None and str(assigned_signer) != str(user.id):
                raise serializers.ValidationError({
                    'fields': (
                        f"assigned_signer {assigned_signer} is not allowed in self-sign envelopes."
                    ),
                })
            normalized_item['assigned_signer'] = user.id
            normalized_fields.append(normalized_item)
        attrs['fields'] = normalized_fields

        signing_order = [{'signer_id': str(user.id), 'order': 1}]
        envelope_payload = {
            'document_ids': [str(doc_id) for doc_id in attrs['document_ids']],
            'name': attrs.get('name', ''),
            'description': attrs.get('description'),
            'signing_order': signing_order,
            'pdf_password_protection_enabled': attrs.get('pdf_password_protection_enabled', True),
            'documents_with_positions': normalized_documents_with_positions,
            'fields': [],
        }
        create_serializer = EnvelopeCreateSerializer(
            data=envelope_payload,
            context=self.context,
        )
        create_serializer.is_valid(raise_exception=True)

        self._validate_self_sign_fields(normalized_fields, envelope_payload['document_ids'])
        attrs['fields'] = normalized_fields

        sign_payload = {
            'signature_id': attrs.get('signature_id'),
            'page': attrs.get('page', 1),
            'x': attrs.get('x', 100),
            'y': attrs.get('y', 100),
            'width': attrs.get('width', 120),
            'height': attrs.get('height', 40),
        }
        if attrs.get('signature_image'):
            sign_payload['signature_image'] = attrs['signature_image']
        sign_serializer = SignDocumentSerializer(data=sign_payload, context=self.context)
        sign_serializer.is_valid(raise_exception=True)

        self._create_serializer = create_serializer
        self._sign_data = sign_serializer.validated_data
        return attrs

    def _validate_self_sign_fields(self, fields_data, document_ids):
        allowed_types = {"initials", "date", "text", "designation"}
        document_ids_in_envelope = set(str(doc_id) for doc_id in document_ids)

        for i, item in enumerate(fields_data):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"fields[{i}] must be an object")

            required_keys = ["document_id", "page", "x", "y", "width", "height", "type", "required"]
            missing = [k for k in required_keys if k not in item]
            if missing:
                raise serializers.ValidationError(f"fields[{i}] missing keys: {missing}")

            doc_id = str(item.get('document_id'))
            if doc_id not in document_ids_in_envelope:
                raise serializers.ValidationError(
                    f"fields[{i}].document_id {doc_id} not in document_ids"
                )

            typ = str(item.get('type'))
            if typ not in allowed_types:
                raise serializers.ValidationError(
                    f"fields[{i}].type must be one of {sorted(list(allowed_types))}"
                )

            try:
                page = int(item.get('page'))
                x = float(item.get('x'))
                y = float(item.get('y'))
                width = float(item.get('width'))
                height = float(item.get('height'))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    f"fields[{i}] numeric fields must be numbers"
                ) from exc
            if page < 1 or x < 0 or y < 0 or width < 0 or height < 0:
                raise serializers.ValidationError(
                    f"fields[{i}] invalid coordinates: page>=1; x,y,width,height>=0"
                )

            if typ in {"text", "designation"}:
                max_length = item.get('max_length')
                if max_length is not None and int(max_length) <= 0:
                    raise serializers.ValidationError(
                        f"fields[{i}].max_length must be positive when provided"
                    )

            if bool(item.get('required')):
                value = item.get('value')
                prefill_value = item.get('prefill_value')
                if value in (None, '') and prefill_value in (None, ''):
                    raise serializers.ValidationError(
                        f"fields[{i}] requires value or prefill_value when required=true"
                    )

    def get_sign_data(self):
        return getattr(self, '_sign_data', {})

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        create_serializer = getattr(self, '_create_serializer')
        envelope_data = create_serializer.validated_data

        document_ids = envelope_data['document_ids']
        documents_with_positions_data = envelope_data.get('documents_with_positions', [])
        fields_data = validated_data.get('fields', [])

        with transaction.atomic():
            envelope = Envelope.objects.create(
                creator=user,
                name=envelope_data.get('name') or None,
                description=envelope_data.get('description'),
                status="draft",
                signing_order=[{'signer_id': str(user.id), 'order': 1}],
                pdf_password_protection_enabled=envelope_data.get(
                    'pdf_password_protection_enabled',
                    True,
                ),
                is_self_sign=True,
            )

            for i, doc_id in enumerate(document_ids, 1):
                document = Document.objects.get(id=doc_id)
                doc_pos_for_envelope_doc = next(
                    (
                        item for item in documents_with_positions_data
                        if str(item['document_id']) == str(doc_id)
                    ),
                    None,
                )
                signer_doc_positions_for_this_doc = []
                if doc_pos_for_envelope_doc:
                    for entry in doc_pos_for_envelope_doc.get('signer_document_positions', []):
                        mutable_entry = entry.copy()
                        if 'signer_id' in mutable_entry:
                            mutable_entry['signer_id'] = str(mutable_entry['signer_id'])
                        signer_doc_positions_for_this_doc.append(mutable_entry)

                EnvelopeDocument.objects.create(
                    envelope=envelope,
                    document=document,
                    order=i,
                    signer_document_positions=signer_doc_positions_for_this_doc,
                )

            if fields_data:
                documents_by_id = {
                    str(doc.id): doc for doc in Document.objects.filter(id__in=document_ids)
                }
                for item in fields_data:
                    doc_id = str(item['document_id'])
                    field_value = item.get('value')
                    prefill_value = item.get('prefill_value')
                    if field_value not in (None, '') and prefill_value in (None, ''):
                        prefill_value = None
                    elif prefill_value not in (None, '') and field_value in (None, ''):
                        field_value = None

                    FieldModel.objects.create(
                        envelope=envelope,
                        document=documents_by_id[doc_id],
                        page=int(item['page']),
                        x=float(item['x']),
                        y=float(item['y']),
                        width=float(item['width']),
                        height=float(item['height']),
                        type=str(item['type']),
                        assigned_signer=user,
                        required=bool(item['required']),
                        prefill_value=prefill_value,
                        value=field_value,
                        placeholder=item.get('placeholder'),
                        font_family=item.get('font_family'),
                        font_size=item.get('font_size'),
                        date_format=item.get('date_format'),
                        max_length=item.get('max_length'),
                    )

        return envelope


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


class SigningJobSerializer(serializers.ModelSerializer):
    """Serializer for async signing job status polling."""

    envelope_id = serializers.UUIDField(source="envelope.id", read_only=True)
    signer_id = serializers.UUIDField(source="signer.id", read_only=True)
    envelope_status = serializers.CharField(source="envelope.status", read_only=True)
    signature = SignatureSerializer(read_only=True, allow_null=True)

    class Meta:
        from signatures.models import SigningJob

        model = SigningJob
        fields = [
            "id",
            "status",
            "envelope_id",
            "signer_id",
            "error_message",
            "attempt_count",
            "created_at",
            "completed_at",
            "envelope_status",
            "signature",
        ]
        read_only_fields = fields
