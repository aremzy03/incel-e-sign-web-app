"""
Views for managing fields (backend-only).
"""

from typing import List
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Field
from .serializers import FieldSerializer, FieldValueSerializer


class EnvelopeFieldsView(APIView):
    """
    List and bulk create/update/delete fields for an envelope document (sender only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, envelope_id):
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        if envelope.creator_id != request.user.id:
            return Response({"status": "error", "message": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = Field.objects.filter(envelope=envelope).order_by('created_at')
        ser = FieldSerializer(qs, many=True)
        return Response({"status": "success", "data": ser.data})

    def post(self, request, envelope_id):
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        if envelope.creator_id != request.user.id:
            return Response({"status": "error", "message": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        if not isinstance(payload, list):
            return Response({"status": "error", "message": "Expected a list payload"}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for item in payload:
            item = dict(item)
            item['envelope'] = str(envelope.id)
            # ensure document belongs to envelope
            from envelopes.models import EnvelopeDocument
            doc_id = item.get('document')
            if not doc_id or not EnvelopeDocument.objects.filter(envelope=envelope, document_id=doc_id).exists():
                return Response({"status": "error", "message": f"Document {doc_id} not in envelope"}, status=status.HTTP_400_BAD_REQUEST)

            field_id = item.get('id')
            if field_id:
                instance = get_object_or_404(Field, pk=field_id, envelope=envelope)
                ser = FieldSerializer(instance, data=item, partial=True)
            else:
                ser = FieldSerializer(data=item)
            ser.is_valid(raise_exception=True)
            obj = ser.save()
            results.append(FieldSerializer(obj).data)

        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)


class SigningFieldsListView(APIView):
    """
    List fields visible to the current signer for an envelope.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, envelope_id):
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        qs = Field.objects.filter(envelope=envelope, assigned_signer=request.user)
        ser = FieldSerializer(qs, many=True)
        return Response({"status": "success", "data": ser.data})


class SigningFieldsValueSaveView(APIView):
    """
    Bulk save signer values for assigned fields.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, envelope_id):
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)

        items = request.data if isinstance(request.data, list) else request.data.get('items')
        if not isinstance(items, list):
            return Response({"status": "error", "message": "Expected a list of {id, value}"}, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        for item in items:
            ser = FieldValueSerializer(data=item)
            ser.is_valid(raise_exception=True)
            f = get_object_or_404(Field, pk=ser.validated_data['id'], envelope=envelope, assigned_signer=request.user)
            # If prefill exists, keep as authoritative; otherwise save value
            if f.prefill_value is None:
                f.value = ser.validated_data.get('value')
                f.save(update_fields=['value', 'updated_at'])
            updated.append(str(f.id))

        return Response({"status": "success", "data": {"updated": updated}})

