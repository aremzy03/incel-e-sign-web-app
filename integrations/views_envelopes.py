"""
Composite envelope create-and-send for first-party partner integrations.

Orchestrates upload (optional) + EnvelopeCreateSerializer + send_envelope so
audit, notifications, and ownership match the three-step partner flow.
"""

from __future__ import annotations

import json
import logging

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.serializers import DocumentUploadSerializer, DocumentSerializer
from envelopes.serializers import EnvelopeCreateSerializer, EnvelopeDetailSerializer
from envelopes.services.send import EnvelopeSendError, send_envelope
from signatures.services.reset_workflow import SigningWorkflowInProgressError

logger = logging.getLogger(__name__)


def _parse_json_field(raw, *, field_name: str, default=None):
    """
    Parse a JSON object/list that may arrive as a string (multipart) or native.
    """
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON") from exc
    raise ValueError(f"{field_name} must be a JSON object or list")


class IntegrationEnvelopeSendView(APIView):
    """
    POST /api/v1/integrations/envelopes/send/

    Auth: user JWT (Bearer) — not client credentials.

    Multipart: ``file`` + envelope fields (signing_order as JSON string).
    JSON: ``document_ids`` + ``signing_order`` (+ optional name/description).

    Idempotency-Key supported.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        from audit.utils import log_action
        from integrations.services.envelope_origin import (
            record_envelope_integration_origin,
        )
        from integrations.services.idempotency import (
            SCOPE_INTEGRATIONS_ENVELOPE_SEND,
            get_idempotency_key,
            lookup_idempotent_response,
            store_idempotent_response,
        )
        from integrations.services.jwt_claims import enrich_message_with_client_id

        idem_key = get_idempotency_key(request)
        if idem_key:
            cached = lookup_idempotent_response(
                user=request.user,
                key=idem_key,
                scope=SCOPE_INTEGRATIONS_ENVELOPE_SEND,
            )
            if cached is not None:
                return cached

        try:
            document_ids, upload_document = self._resolve_documents(request)
            create_payload = self._build_create_payload(request, document_ids)
        except ValueError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_serializer = EnvelopeCreateSerializer(
            data=create_payload,
            context={"request": request},
        )
        if not create_serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed",
                    "data": create_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        envelope = create_serializer.save()

        create_message = (
            f"User {request.user.full_name or request.user.username} "
            f"created envelope '{envelope.name}' with "
            f"{envelope.envelopedocument_set.count()} documents."
        )
        log_action(
            request.user,
            "CREATE_ENVELOPE",
            envelope,
            enrich_message_with_client_id(create_message, request),
            request=request,
        )
        record_envelope_integration_origin(envelope, request=request)

        try:
            envelope = send_envelope(envelope, user=request.user, request=request)
        except SigningWorkflowInProgressError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except EnvelopeSendError as exc:
            return Response(
                {"status": "error", "message": exc.message},
                status=exc.status_code,
            )

        detail = EnvelopeDetailSerializer(envelope).data
        document_data = None
        if upload_document is not None:
            document_data = DocumentSerializer(upload_document).data

        body = {
            "status": "success",
            "message": "Envelope created and sent successfully",
            "data": {
                "envelope_id": str(envelope.id),
                "document_ids": [
                    str(doc_id)
                    for doc_id in envelope.envelopedocument_set.order_by(
                        "order"
                    ).values_list("document_id", flat=True)
                ],
                "status": envelope.status,
                "envelope": detail,
                "uploaded_document": document_data,
            },
        }
        if idem_key:
            store_idempotent_response(
                user=request.user,
                key=idem_key,
                scope=SCOPE_INTEGRATIONS_ENVELOPE_SEND,
                response_status=status.HTTP_201_CREATED,
                response_body=body,
                envelope_id=envelope.id,
            )
        return Response(body, status=status.HTTP_201_CREATED)

    def _resolve_documents(self, request):
        """
        Return (document_ids, uploaded_document_or_None).

        Accepts either an uploaded ``file`` or existing ``document_ids``.
        """
        upload_file = request.FILES.get("file")
        raw_ids = request.data.get("document_ids")

        if upload_file is not None:
            upload_serializer = DocumentUploadSerializer(data={"file": upload_file})
            if not upload_serializer.is_valid():
                raise ValueError(
                    f"Invalid file data: {upload_serializer.errors}"
                )
            document = upload_serializer.save(owner=request.user)

            from audit.utils import log_action

            log_action(
                request.user,
                "UPLOAD_DOC",
                document,
                (
                    f"User {request.user.full_name or request.user.username} "
                    f"uploaded document '{document.file_name}'."
                ),
                request=request,
            )
            return [str(document.id)], document

        try:
            document_ids = _parse_json_field(
                raw_ids,
                field_name="document_ids",
                default=None,
            )
        except ValueError:
            # Allow comma-separated UUID string as a convenience for form posts.
            if isinstance(raw_ids, str) and raw_ids.strip():
                document_ids = [part.strip() for part in raw_ids.split(",") if part.strip()]
            else:
                raise

        if not document_ids:
            raise ValueError(
                "Provide either a multipart file or document_ids."
            )
        if not isinstance(document_ids, list):
            raise ValueError("document_ids must be a list of UUIDs.")
        return [str(doc_id) for doc_id in document_ids], None

    def _build_create_payload(self, request, document_ids: list[str]) -> dict:
        """Assemble EnvelopeCreateSerializer input from JSON or multipart fields."""
        try:
            signing_order = _parse_json_field(
                request.data.get("signing_order"),
                field_name="signing_order",
                default=[],
            )
            documents_with_positions = _parse_json_field(
                request.data.get("documents_with_positions"),
                field_name="documents_with_positions",
                default=None,
            )
            fields = _parse_json_field(
                request.data.get("fields"),
                field_name="fields",
                default=None,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if signing_order is None:
            signing_order = []

        payload = {
            "document_ids": document_ids,
            "signing_order": signing_order,
        }
        if "name" in request.data:
            payload["name"] = request.data.get("name")
        if "description" in request.data:
            payload["description"] = request.data.get("description")
        if "pdf_password_protection_enabled" in request.data:
            raw = request.data.get("pdf_password_protection_enabled")
            if isinstance(raw, str):
                payload["pdf_password_protection_enabled"] = raw.strip().lower() in (
                    "1",
                    "true",
                    "yes",
                )
            else:
                payload["pdf_password_protection_enabled"] = bool(raw)
        if documents_with_positions is not None:
            payload["documents_with_positions"] = documents_with_positions
        if fields is not None:
            payload["fields"] = fields
        return payload
