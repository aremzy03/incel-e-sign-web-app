"""
Current-signer additive text.

This is not the draft editor. It bakes text into the shared document while the
envelope is pending, and only for the signer whose turn it is.
"""

from __future__ import annotations

import os
import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import DocumentRevision
from documents.services.pdf_files import delete_storage_url, download_pdf_to_temp, temp_pdf_file, upload_text_edit_pdf
from documents.services.pdf_text import PdfEditError, apply_add_text, drawable_ops, inspect_pdf, validate_add_text_ops
from documents.text_edit_views import _error
from envelopes.models import Envelope, EnvelopeDocument


def _same_stored_file(stored: str, client: str) -> bool:
    if not client or stored == client:
        return True
    stored_path = stored.split("?", 1)[0]
    client_path = client.split("?", 1)[0]
    if stored_path == client_path:
        return True
    try:
        from documents.services.pdf_files import resolve_s3_key_from_url

        return resolve_s3_key_from_url(stored) == resolve_s3_key_from_url(client)
    except (ValueError, Exception):
        return False


def _resolve_signer(request, envelope: Envelope):
    from envelopes.services.signing_token import validate_signing_token

    token_str = (
        request.data.get("token")
        or request.query_params.get("token")
        or request.headers.get("X-Signing-Token")
    )
    if token_str:
        signing_token, error_code, error_message = validate_signing_token(
            token_str, envelope_id=str(envelope.id)
        )
        if error_code:
            status_code = status.HTTP_403_FORBIDDEN
            if error_code == "TOKEN_EXPIRED":
                status_code = status.HTTP_410_GONE
            if error_code in ("MISSING_TOKEN", "INVALID_TOKEN"):
                status_code = status.HTTP_400_BAD_REQUEST
            return None, Response(
                {"status": "error", "code": error_code, "message": error_message},
                status=status_code,
            )
        user = signing_token.recipient_user
        email = signing_token.recipient_email
    elif request.user and request.user.is_authenticated:
        user = request.user
        email = request.user.email
    else:
        return None, Response({"status": "error", "message": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

    signature = None
    if user:
        signature = envelope.signatures.filter(signer=user).first()
    if signature is None and email:
        signature = envelope.signatures.filter(signer__email__iexact=email).first()
    if signature is None or not signature.is_current_signer():
        return None, Response(
            {"status": "error", "message": "Only the current signer can add text."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return signature, None


class RecipientAddTextView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, envelope_id, document_id):
        envelope = Envelope.objects.filter(pk=envelope_id, status="pending").first()
        if envelope is None:
            return Response({"status": "error", "message": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not envelope.allow_recipient_text:
            return Response(
                {"status": "error", "reason": "flag_off", "message": "Recipients can’t add text on this envelope."},
                status=status.HTTP_403_FORBIDDEN,
            )
        link = EnvelopeDocument.objects.filter(envelope=envelope, document_id=document_id).select_related("document").first()
        if link is None:
            return Response({"status": "error", "message": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        signature, error_response = _resolve_signer(request, envelope)
        if error_response is not None:
            return error_response

        document = link.document
        ops = request.data.get("ops") if isinstance(request.data, dict) else None
        local_path = None
        try:
            local_path = download_pdf_to_temp(document.file_url)
            inspection = inspect_pdf(str(local_path))
        except PdfEditError as exc:
            return _error(exc.reason, exc.status_code, exc.extra)
        except FileNotFoundError:
            return _error("unreadable_pdf", status.HTTP_422_UNPROCESSABLE_ENTITY)
        finally:
            if local_path is not None:
                try:
                    os.remove(local_path)
                except OSError:
                    pass

        errors = validate_add_text_ops(ops if isinstance(ops, list) else [], inspection["pages"])
        if not isinstance(ops, list) or errors:
            return Response(
                {"status": "error", "errors": errors or [{"opId": None, "reason": "invalid_ops"}]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not drawable_ops(ops):
            return Response(
                {
                    "status": "success",
                    "data": {
                        "document_id": str(document.id),
                        "file_url": document.file_url,
                        "file_size": document.file_size,
                        "revision_id": None,
                    },
                }
            )

        client_base = request.data.get("base_file_url") if isinstance(request.data, dict) else None
        if client_base and not _same_stored_file(document.file_url, client_base):
            return _error("base_changed", status.HTTP_409_CONFLICT)

        source = None
        new_url = None
        revision_key = uuid.uuid4()
        try:
            source = download_pdf_to_temp(document.file_url)
            with temp_pdf_file() as dest:
                apply_add_text(str(source), str(dest), ops)
                file_size = dest.stat().st_size
                new_url = upload_text_edit_pdf(document.id, revision_key, dest)
            with transaction.atomic():
                revision = DocumentRevision.objects.create(
                    document=document,
                    file_url=new_url,
                    file_size=file_size,
                    source="recipient_add_text",
                )
                if not document.revisions.filter(source="upload").exists():
                    DocumentRevision.objects.create(
                        document=document,
                        file_url=document.file_url,
                        file_size=document.file_size,
                        source="upload",
                    )
                document.file_url = new_url
                document.file_size = file_size
                document.save(update_fields=["file_url", "file_size", "updated_at"])
        except PdfEditError as exc:
            if new_url:
                delete_storage_url(new_url)
            return _error(exc.reason, exc.status_code, exc.extra)
        except Exception:
            if new_url:
                delete_storage_url(new_url)
            raise
        finally:
            if source is not None:
                try:
                    os.remove(source)
                except OSError:
                    pass

        try:
            from audit.utils import log_action

            log_action(
                signature.signer,
                "RECIPIENT_ADD_TEXT",
                envelope,
                f"Signer added text to {document.file_name}.",
                request=request,
            )
        except Exception:
            pass

        return Response(
            {
                "status": "success",
                "data": {
                    "document_id": str(document.id),
                    "file_url": document.file_url,
                    "file_size": document.file_size,
                    "revision_id": str(revision.id),
                },
            }
        )
