"""
Serializers for the fields app.
"""

from rest_framework import serializers
from .models import Field


class FieldSerializer(serializers.ModelSerializer):
    """
    Serializer for Field CRUD and retrieval.
    """

    class Meta:
        model = Field
        fields = [
            'id', 'envelope', 'document', 'page', 'x', 'y', 'width', 'height',
            'type', 'assigned_signer', 'required', 'prefill_value', 'value',
            'placeholder', 'font_family', 'font_size', 'date_format', 'max_length',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        field_type = attrs.get('type') or getattr(self.instance, 'type', None)
        prefill_value = attrs.get('prefill_value', getattr(self.instance, 'prefill_value', None))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        max_length = attrs.get('max_length', getattr(self.instance, 'max_length', None))
        date_format = attrs.get('date_format', getattr(self.instance, 'date_format', None))

        if field_type in ('text', 'designation') and max_length is not None:
            if max_length <= 0:
                raise serializers.ValidationError({'max_length': 'max_length must be positive.'})

        def _validate_text(val):
            if val is None:
                return
            if max_length is not None and len(str(val)) > max_length:
                raise serializers.ValidationError({'value': f'Value exceeds max_length {max_length}.'})

        def _validate_date(val):
            if val is None:
                return
            # store any provided date as-is; UI/backend can enforce formatting contract
            # basic sanity check length
            if len(str(val)) > 64:
                raise serializers.ValidationError({'value': 'Date value too long.'})

        if field_type in ('text', 'designation', 'initials'):
            _validate_text(prefill_value)
            _validate_text(value)
        elif field_type == 'date':
            _validate_date(prefill_value)
            _validate_date(value)

        return attrs


class FieldValueSerializer(serializers.Serializer):
    """
    Serializer for signer submitting values for assigned fields.
    Accepts list of {id, value}.
    """

    id = serializers.UUIDField()
    value = serializers.CharField(allow_blank=True, required=False, allow_null=True)

