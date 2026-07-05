"""
Serializers for the envelopes app.

This module defines serializers for envelope-related operations
in the e-signature workflow.
"""

from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Envelope, EnvelopeDocument
from documents.models import Document
from documents.storage import refresh_remote_file_url
from signatures.serializers import SignatureSerializer # Import SignatureSerializer
from fields.serializers import FieldSerializer
import uuid
from django.db import transaction
from fields.models import Field as FieldModel

User = get_user_model()


class PositionSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=True)
    x = serializers.FloatField(min_value=0.0, required=True)
    y = serializers.FloatField(min_value=0.0, required=True)
    width = serializers.FloatField(min_value=0.0, required=True)
    height = serializers.FloatField(min_value=0.0, required=True)

class SignerDocumentPositionSerializer(serializers.Serializer):
    signer_id = serializers.UUIDField(required=True)
    position = PositionSerializer()

class DocumentWithPositionsSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(required=True)
    signer_document_positions = serializers.ListField(
        child=SignerDocumentPositionSerializer(),
        required=False,
        allow_empty=True
    )

class EnvelopeCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new envelopes.
    
    Validates document ownership and signing order before creating
    an envelope with status="draft".
    """
    
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        min_length=1,
        help_text="List of UUIDs of the documents to include in the envelope."
    )
    
    name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional user-defined name for the envelope."
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional description or notes for recipients about this envelope."
    )
    
    signing_order = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True,
        help_text="List of signers in order: [{'signer_id': 'uuid', 'order': 1}, ...]. Document-specific positions are in EnvelopeDocument."
    )

    # New field to accept document-specific signer positions
    documents_with_positions = serializers.ListField(
        child=DocumentWithPositionsSerializer(),
        required=False,
        allow_empty=True,
        write_only=True,
        help_text="Optional list of document_ids with their respective signer-document-positions."
    )

    # New: fields to be created atomically with the envelope
    fields = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        write_only=True,
        help_text="Optional list of non-signature fields to create with the envelope."
    )

    class Meta:
        model = Envelope
        fields = [
            'document_ids',
            'name',
            'description',
            'signing_order',
            'pdf_password_protection_enabled',
            'documents_with_positions',
            'fields',
        ]

    def validate_document_ids(self, value):
        """
        Validate that all documents exist and belong to the request user.
        """
        if not value:
            raise serializers.ValidationError("At least one document ID is required.")

        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            raise serializers.ValidationError("User authentication required.")
        user = request.user

        # Filter existing documents owned by the user
        existing_docs = Document.objects.filter(id__in=value, owner=user)
        if existing_docs.count() != len(value):
            # Identify missing or unauthorized documents
            existing_doc_ids = set(str(d.id) for d in existing_docs)
            provided_doc_ids = set(str(uid) for uid in value)
            missing_or_unauthorized_ids = provided_doc_ids - existing_doc_ids
            raise serializers.ValidationError(
                f"Some documents not found or do not belong to you: {list(missing_or_unauthorized_ids)}"
            )

        return value

    def validate_signing_order(self, value):
        """
        Validate the signing_order field.

        Ensures:
        - signing_order is a list of dictionaries
        - Each dict has 'signer_id' and 'order' keys
        - Orders start from 1 and are unique (no duplicates, no gaps)
        - signer_id values correspond to existing users
        """
        if not isinstance(value, list):
            raise serializers.ValidationError('Signing order must be a list.')

        if not value:
            return value # Empty list is valid (no signers yet)

        signer_ids = set()
        orders = []

        for i, signer_entry in enumerate(value):
            if not isinstance(signer_entry, dict):
                raise serializers.ValidationError(f'Entry {i} must be a dictionary.')

            if 'signer_id' not in signer_entry or 'order' not in signer_entry:
                raise serializers.ValidationError(f'Entry {i} must have both "signer_id" and "order" keys.')

            signer_id = signer_entry['signer_id']
            order = signer_entry['order']

            try:
                uuid.UUID(str(signer_id))
            except (ValueError, TypeError):
                raise serializers.ValidationError(f'Entry {i}: signer_id must be a valid UUID.')

            if not isinstance(order, int) or order < 1:
                raise serializers.ValidationError(f'Entry {i}: order must be a positive integer.')

            if signer_id in signer_ids:
                raise serializers.ValidationError(f'Duplicate signer_id found: {signer_id}')
            signer_ids.add(signer_id)

            if order in orders:
                raise serializers.ValidationError(f'Duplicate order found: {order}')
            orders.append(order)

        if orders:
            orders.sort()
            expected_orders = list(range(1, len(orders) + 1))
            if orders != expected_orders:
                raise serializers.ValidationError('Orders must start from 1 and have no gaps.')

        # Validate that all signer_ids correspond to existing users
        from django.contrib.auth import get_user_model
        User = get_user_model()
        existing_user_ids = set(str(user_id) for user_id in 
                                User.objects.filter(id__in=[uuid.UUID(str(s_id)) for s_id in signer_ids]).values_list('id', flat=True))
        missing_user_ids = signer_ids - existing_user_ids
        if missing_user_ids:
            raise serializers.ValidationError(f'Users not found: {list(missing_user_ids)}')

        return value

    def validate_documents_with_positions(self, value):
        document_ids_in_envelope = set(str(doc_id) for doc_id in self.initial_data.get('document_ids', []))
        for entry in value:
            doc_id = str(entry['document_id'])
            if doc_id not in document_ids_in_envelope:
                raise serializers.ValidationError(f"Document ID {doc_id} in documents_with_positions is not part of the envelope's document_ids.")

            signer_ids_in_envelope = set(str(s['signer_id']) for s in self.initial_data.get('signing_order', []))
            for signer_pos in entry.get('signer_document_positions', []):
                signer_id = str(signer_pos['signer_id'])
                if signer_id not in signer_ids_in_envelope:
                    raise serializers.ValidationError(f"Signer ID {signer_id} in signer_document_positions for document {doc_id} is not part of the envelope's signing_order.")
        return value

    def validate_fields(self, value):
        # Basic schema validation for field items
        allowed_types = {"initials", "date", "text", "designation"}
        document_ids_in_envelope = set(str(doc_id) for doc_id in self.initial_data.get('document_ids', []))
        signer_ids_in_envelope = set(str(s['signer_id']) for s in self.initial_data.get('signing_order', []))

        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"fields[{i}] must be an object")

            # Required keys
            required_keys = ["document_id", "page", "x", "y", "width", "height", "type", "assigned_signer", "required"]
            missing = [k for k in required_keys if k not in item]
            if missing:
                raise serializers.ValidationError(f"fields[{i}] missing keys: {missing}")

            # Validate document id membership
            doc_id = str(item.get('document_id'))
            if doc_id not in document_ids_in_envelope:
                raise serializers.ValidationError(f"fields[{i}].document_id {doc_id} not in document_ids")

            # Validate signer membership
            signer_id = str(item.get('assigned_signer'))
            if signer_id not in signer_ids_in_envelope:
                raise serializers.ValidationError(f"fields[{i}].assigned_signer {signer_id} not in signing_order")

            # Type
            typ = str(item.get('type'))
            if typ not in allowed_types:
                raise serializers.ValidationError(f"fields[{i}].type must be one of {sorted(list(allowed_types))}")

            # Numerics
            try:
                page = int(item.get('page'))
                x = float(item.get('x'))
                y = float(item.get('y'))
                width = float(item.get('width'))
                height = float(item.get('height'))
            except Exception:
                raise serializers.ValidationError(f"fields[{i}] numeric fields must be numbers")
            if page < 1 or x < 0 or y < 0 or width < 0 or height < 0:
                raise serializers.ValidationError(f"fields[{i}] invalid coordinates: page>=1; x,y,width,height>=0")

            # Text constraints
            if typ in {"text", "designation"}:
                max_length = item.get('max_length')
                if max_length is not None and int(max_length) <= 0:
                    raise serializers.ValidationError(f"fields[{i}].max_length must be positive when provided")

            # Date value sanity
            if typ == "date":
                dv = item.get('prefill_value')
                if dv is not None and len(str(dv)) > 64:
                    raise serializers.ValidationError(f"fields[{i}].prefill_value too long for date")

        return value

    def create(self, validated_data):
        document_ids = validated_data.pop('document_ids')
        name = validated_data.pop('name', None)
        description = validated_data.pop('description', None)
        signing_order = validated_data.pop('signing_order', [])
        pdf_password_protection_enabled = validated_data.pop('pdf_password_protection_enabled', True)
        documents_with_positions_data = validated_data.pop('documents_with_positions', [])
        fields_data = validated_data.pop('fields', [])

        request = self.context.get('request')
        creator = request.user if request else None

        if not creator:
            raise serializers.ValidationError("User authentication required.")

        with transaction.atomic():
            envelope = Envelope.objects.create(
                creator=creator,
                name=name,
                description=description,
                status="draft",
                signing_order=signing_order,
                pdf_password_protection_enabled=pdf_password_protection_enabled,
            )

            # Add documents to the envelope via the intermediary model
            for i, doc_id in enumerate(document_ids, 1):
                document = Document.objects.get(id=doc_id)

                # Find corresponding signer_document_positions for this document
                doc_pos_for_envelope_doc = next(
                    (item for item in documents_with_positions_data if str(item['document_id']) == str(doc_id)),
                    None
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
                    signer_document_positions=signer_doc_positions_for_this_doc
                )

            # Create fields if provided
            if fields_data:
                # Map documents for quick lookup and ensure membership already validated
                documents_by_id = {str(doc.id): doc for doc in Document.objects.filter(id__in=document_ids)}
                signer_ids_in_envelope = {str(s['signer_id']) for s in signing_order}

                for item in fields_data:
                    doc_id = str(item['document_id'])
                    assigned_signer_id = str(item['assigned_signer'])
                    # Safety checks (should have been validated above)
                    if doc_id not in documents_by_id or assigned_signer_id not in signer_ids_in_envelope:
                        raise serializers.ValidationError("Invalid field references to document or signer.")

                    FieldModel.objects.create(
                        envelope=envelope,
                        document=documents_by_id[doc_id],
                        page=int(item['page']),
                        x=float(item['x']),
                        y=float(item['y']),
                        width=float(item['width']),
                        height=float(item['height']),
                        type=str(item['type']),
                        assigned_signer_id=assigned_signer_id,
                        required=bool(item['required']),
                        prefill_value=item.get('prefill_value'),
                        placeholder=item.get('placeholder'),
                        font_family=item.get('font_family'),
                        font_size=item.get('font_size'),
                        date_format=item.get('date_format'),
                        max_length=item.get('max_length'),
                    )

        return envelope


class EnvelopeDocumentSerializer(serializers.ModelSerializer):
    document_file_name = serializers.CharField(source='document.file_name', read_only=True)
    document_file_url = serializers.CharField(source='document.file_url', read_only=True)
    document_signed_file_url = serializers.CharField(source='document.signed_file_url', read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(settings, "USE_S3", False):
            if data.get("document_file_url"):
                data["document_file_url"] = refresh_remote_file_url(data["document_file_url"])
            if data.get("document_signed_file_url"):
                data["document_signed_file_url"] = refresh_remote_file_url(
                    data["document_signed_file_url"]
                )
        return data

    class Meta:
        model = EnvelopeDocument
        fields = ['id', 'document', 'order', 'document_file_name', 'document_file_url', 'document_signed_file_url', 'signer_document_positions']
        read_only_fields = fields


def _user_display_name(user) -> str:
    """Return full_name when set, otherwise username."""
    return user.full_name or user.username


def _enrich_signing_order(signing_order, user_by_id=None):
    """
    Return signing_order entries with signer_name resolved from user records.

    Each entry includes signer_id, order, and signer_name (or null if unknown).
    """
    if not signing_order:
        return []

    if user_by_id is None:
        signer_ids = [
            entry.get('signer_id')
            for entry in signing_order
            if entry.get('signer_id')
        ]
        user_by_id = {
            str(user.id): user
            for user in User.objects.filter(id__in=signer_ids)
        }

    enriched_order = []
    for entry in signing_order:
        signer_id = str(entry.get('signer_id', ''))
        signer = user_by_id.get(signer_id)
        enriched_order.append({
            'signer_id': signer_id,
            'order': entry.get('order'),
            'signer_name': _user_display_name(signer) if signer else None,
        })
    return enriched_order


def _get_envelope_current_signer(envelope):
    """
    Return the signer who must act next for a pending envelope, or None.

    The current signer is the pending signature with the lowest signing order.
    """
    if envelope.status != 'pending':
        return None

    pending_signatures = [s for s in envelope.signatures.all() if s.status == 'pending']
    if not pending_signatures:
        return None

    current_signature = min(pending_signatures, key=lambda signature: signature.get_signing_order())
    signer = current_signature.signer
    return {
        'id': str(signer.id),
        'name': _user_display_name(signer),
        'email': signer.email,
    }


class EnvelopeListListSerializer(serializers.ListSerializer):
    """Batch-resolve signer names for signing_order across a paginated list."""

    def to_representation(self, data):
        iterable = data.all() if hasattr(data, 'all') else data
        envelopes = list(iterable)

        signer_ids = set()
        for envelope in envelopes:
            for entry in envelope.signing_order or []:
                if entry.get('signer_id'):
                    signer_ids.add(str(entry['signer_id']))

        user_by_id = {
            str(user.id): user
            for user in User.objects.filter(id__in=signer_ids)
        } if signer_ids else {}

        self.child.context['signer_user_by_id'] = user_by_id
        return super().to_representation(envelopes)


class EnvelopeListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for paginated envelope list responses.

    Returns only the fields needed to render envelope list cards in the UI.
    """

    creator_name = serializers.SerializerMethodField()
    signing_order = serializers.SerializerMethodField()
    signer_count = serializers.SerializerMethodField()
    current_signer = serializers.SerializerMethodField()

    class Meta:
        model = Envelope
        fields = [
            'id', 'creator', 'creator_name', 'name', 'status',
            'is_self_sign', 'signing_order', 'signer_count',
            'current_signer', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
        list_serializer_class = EnvelopeListListSerializer

    def get_creator_name(self, obj):
        return _user_display_name(obj.creator)

    def get_signing_order(self, obj):
        user_by_id = self.context.get('signer_user_by_id')
        return _enrich_signing_order(obj.signing_order, user_by_id)

    def get_signer_count(self, obj):
        return len(obj.signing_order)

    def get_current_signer(self, obj):
        return _get_envelope_current_signer(obj)


class EnvelopeDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for envelope details (read-only).
    
    Includes details of associated documents and signature statuses.
    """
    
    creator_email = serializers.CharField(source='creator.email', read_only=True)
    documents = EnvelopeDocumentSerializer(source='envelopedocument_set', many=True, read_only=True)
    fields = FieldSerializer(many=True, read_only=True)
    signatures = SignatureSerializer(many=True, read_only=True)
    signer_count = serializers.SerializerMethodField()
    current_signer = serializers.SerializerMethodField()
    pdf_lock_password = serializers.CharField(read_only=True, allow_null=True)
    pdf_password_protection_enabled = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Envelope
        fields = [
            'id', 'creator', 'creator_email', 'name', 'description', 'status',
            'is_self_sign', 'signing_order', 'signer_count', 'current_signer',
            'documents', 'fields', 'signatures',
            'pdf_lock_password',
            'pdf_password_protection_enabled',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'creator', 'name', 'description', 'status', 'created_at', 'updated_at'
        ]
    
    def get_signer_count(self, obj):
        return len(obj.signing_order)

    def get_current_signer(self, obj):
        return _get_envelope_current_signer(obj)


class EnvelopeUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating draft or rejected envelopes.
    
    Allows updating `name`, `document_ids`, and `signing_order`.
    """
    
    name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional user-defined name for the envelope."
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional description or notes for recipients about this envelope."
    )

    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        min_length=1,
        help_text="List of UUIDs of the documents to include in the envelope."
    )

    signing_order = EnvelopeCreateSerializer().fields['signing_order']

    documents_with_positions = EnvelopeCreateSerializer().fields['documents_with_positions']

    class Meta:
        model = Envelope
        fields = [
            'name',
            'description',
            'document_ids',
            'signing_order',
            'pdf_password_protection_enabled',
            'documents_with_positions',
        ]

    def _current_document_ids(self):
        if 'document_ids' in self.initial_data:
            return [str(doc_id) for doc_id in self.initial_data.get('document_ids', [])]
        if self.instance:
            return [str(doc_id) for doc_id in self.instance.envelopedocument_set.order_by('order').values_list('document_id', flat=True)]
        return []

    def _current_signing_order(self):
        if 'signing_order' in self.initial_data:
            return self.initial_data.get('signing_order', [])
        if self.instance:
            return self.instance.signing_order or []
        return []

    def _build_create_serializer(self, *, document_ids=None, signing_order=None, documents_with_positions=None, fields=None):
        helper_data = {
            'document_ids': document_ids if document_ids is not None else self._current_document_ids(),
            'signing_order': signing_order if signing_order is not None else self._current_signing_order(),
            'documents_with_positions': documents_with_positions if documents_with_positions is not None else [],
            'fields': fields if fields is not None else []
        }
        return EnvelopeCreateSerializer(data=helper_data, context=self.context)

    def validate_document_ids(self, value):
        # Reuse validation from EnvelopeCreateSerializer
        helper = self._build_create_serializer(document_ids=[str(doc_id) for doc_id in value])
        return helper.validate_document_ids(value)

    def validate_signing_order(self, value):
        # Reuse the same validation logic as creation
        helper = self._build_create_serializer(signing_order=value)
        return helper.validate_signing_order(value)

    def validate_documents_with_positions(self, value):
        # Reuse validation from EnvelopeCreateSerializer
        helper = self._build_create_serializer(documents_with_positions=value)
        return helper.validate_documents_with_positions(value)

    def update(self, instance, validated_data):
        document_ids = validated_data.pop('document_ids', None)
        documents_with_positions_data = validated_data.pop('documents_with_positions', None)

        # Update simple fields
        instance.name = validated_data.get('name', instance.name)
        if 'description' in validated_data:
            instance.description = validated_data.get('description')
        instance.signing_order = validated_data.get('signing_order', instance.signing_order)
        if 'pdf_password_protection_enabled' in validated_data:
            instance.pdf_password_protection_enabled = validated_data.get(
                'pdf_password_protection_enabled',
                instance.pdf_password_protection_enabled,
            )

        # Update documents and their positions if provided
        if document_ids is not None:
            # Clear existing EnvelopeDocument relations
            instance.envelopedocument_set.all().delete()
            
            # Add new EnvelopeDocument relations
            for i, doc_id in enumerate(document_ids, 1):
                document = Document.objects.get(id=doc_id)
                
                # Find corresponding signer_document_positions for this document
                signer_doc_positions = []
                if documents_with_positions_data:
                    doc_pos_for_envelope_doc = next(
                        (item for item in documents_with_positions_data if str(item['document_id']) == str(doc_id)),
                        None
                    )
                    if doc_pos_for_envelope_doc:
                        for entry in doc_pos_for_envelope_doc.get('signer_document_positions', []):
                            # Ensure signer_id is a string for JSONField compatibility
                            if 'signer_id' in entry:
                                entry['signer_id'] = str(entry['signer_id'])
                            signer_doc_positions.append(entry)

                EnvelopeDocument.objects.create(
                    envelope=instance,
                    document=document,
                    order=i,
                    signer_document_positions=signer_doc_positions
                )

        instance.full_clean()
        instance.save(update_fields=list(validated_data.keys()) + ['updated_at'])
        return instance

class EnvelopeSerializer(serializers.ModelSerializer):
    """
    Serializer for envelope details (read-only).
    
    Used for returning envelope data in send/reject operations and retrieval.
    Includes nested signature and document information.
    """
    
    signatures = SignatureSerializer(many=True, read_only=True)
    documents = EnvelopeDocumentSerializer(source='envelopedocument_set', many=True, read_only=True)
    signer_count = serializers.SerializerMethodField()
    pdf_lock_password = serializers.CharField(read_only=True, allow_null=True)
    pdf_password_protection_enabled = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Envelope
        fields = [
            'id', 'creator', 'name', 'description', 'status', 'signing_order', 
            'signer_count', 'documents', 'signatures', 'pdf_lock_password',
            'pdf_password_protection_enabled',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'creator', 'name', 'description', 'status', 'signing_order', 
            'signer_count', 'documents', 'signatures', 'pdf_lock_password',
            'pdf_password_protection_enabled',
            'created_at', 'updated_at'
        ]
    
    def get_signer_count(self, obj):
        return len(obj.signing_order)


class DashboardActivitySerializer(serializers.Serializer):
    """Serializer for a single dashboard activity entry derived from an audit log."""

    id = serializers.UUIDField()
    action = serializers.CharField()
    envelope_id = serializers.UUIDField(allow_null=True)
    envelope_name = serializers.CharField(allow_null=True)
    message = serializers.CharField()
    created_at = serializers.DateTimeField()

    @staticmethod
    def from_audit_log(log):
        """Build a dashboard activity dict from an AuditLog instance."""
        target = log.target_object
        envelope = None
        if target is not None:
            envelope = getattr(target, 'envelope', target)

        return {
            'id': log.id,
            'action': log.action,
            'envelope_id': str(envelope.id) if envelope else None,
            'envelope_name': envelope.name if envelope else None,
            'message': log.message,
            'created_at': log.created_at,
        }
