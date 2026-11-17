"""
Draft additive-text sessions.

The client sends operations. The server opens the stored PDF and bakes them.
Pending envelopes and non-draft documents are refused here. Recipient typing
uses a separate signing endpoint.
"""

from __future__ import annotations

import os

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Document, DocumentEditSession, DocumentRevision
from documents.services.pdf_files import (
    delete_storage_url,
    download_pdf_to_temp,
    temp_pdf_file,
    upload_text_edit_pdf,
)
from documents.services.pdf_text import (
    MAX_FILE_BYTES,
    PdfEditError,
    apply_add_text,
    drawable_ops,
    inspect_pdf,
    validate_add_text_ops,
)

EDIT_COPY = {
    "not_draft": "Only draft documents can be edited.",
    "pending_envelope": "This document is in an envelope that’s still out for signature.",
    "rotated_pages": "This PDF’s pages are rotated. Rotate it upright before adding text.",
    "encrypted": "This PDF is protected and can’t be edited.",
    "unreadable_pdf": "This file couldn’t be opened as a PDF.",
    "base_changed": "This document was updated. Your text was not applied.",
    "unsupported_character": "This font can’t draw one of the characters in a text box.",
    "too_large": "This document is too large to edit here (limit 200 pages or 50 MB).",
}


def _error(reason: str, status_code: int, extra: dict | None = None) -> Response:
    payload = {"status": "error", "reason": reason, "message": EDIT_COPY.get(reason, reason)}
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def _owned_document(request, document_id):
    return Document.objects.filter(pk=document_id, owner=request.user).first()


def _not_found():
    return Response({"status": "error", "message": "Not found"}, status=status.HTTP_404_NOT_FOUND)


def assert_document_editable(document: Document) -> dict:
    """
    Guards shared by every draft text-edit route.

    The caller has already restricted the document to its owner.
    """
    if document.status != "draft":
        raise PdfEditError("not_draft", status.HTTP_409_CONFLICT)
    from envelopes.models import EnvelopeDocument

    if EnvelopeDocument.objects.filter(document=document, envelope__status="pending").exists():
        raise PdfEditError("pending_envelope", status.HTTP_409_CONFLICT)
    if (document.file_size or 0) > MAX_FILE_BYTES:
        raise PdfEditError("too_large", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    local_path = None
    try:
        local_path = download_pdf_to_temp(document.file_url)
        return inspect_pdf(str(local_path))
    except FileNotFoundError as exc:
        raise PdfEditError("unreadable_pdf", status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
    finally:
        if local_path is not None:
            try:
                os.remove(local_path)
            except OSError:
                pass


def _session_payload(session: DocumentEditSession, inspection: dict | None = None) -> dict:
    pages = inspection["pages"] if inspection else session.page_meta
    page_count = inspection["page_count"] if inspection else len(session.page_meta or [])
    return {
        "session_id": str(session.id),
        "base_file_url": session.base_file_url,
        "page_count": page_count,
        "pages": pages,
        "ops": session.ops or [],
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _open_session(document: Document, user) -> DocumentEditSession | None:
    return (
        DocumentEditSession.objects.filter(
            document=document,
            owner=user,
            status=DocumentEditSession.Status.OPEN,
        )
        .order_by("-updated_at")
        .first()
    )


def _ensure_upload_revision(document: Document) -> None:
    if document.revisions.exists():
        return
    DocumentRevision.objects.create(
        document=document,
        file_url=document.file_url,
        file_size=document.file_size,
        source="upload",
    )


def _base_changed(session: DocumentEditSession, document: Document) -> bool:
    return document.file_url != session.base_file_url


class DocumentTextEditSessionView(APIView):
    """Open, autosave, or discard the caller's additive-text session."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        document = _owned_document(request, pk)
        if document is None:
            return _not_found()
        try:
            inspection = assert_document_editable(document)
        except PdfEditError as exc:
            return _error(exc.reason, exc.status_code, exc.extra)

        existing = _open_session(document, request.user)
        if existing is not None:
            return Response({"status": "success", "data": _session_payload(existing, inspection)})

        _ensure_upload_revision(document)
        session = DocumentEditSession.objects.create(
            document=document,
            owner=request.user,
            base_file_url=document.file_url,
            ops=[],
            page_meta=inspection["pages"],
        )
        return Response(
            {"status": "success", "data": _session_payload(session, inspection)},
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        document = _owned_document(request, pk)
        if document is None:
            return _not_found()
        session = _open_session(document, request.user)
        if session is None:
            return _not_found()
        if _base_changed(session, document):
            return _error("base_changed", status.HTTP_409_CONFLICT)
        ops = request.data.get("ops") if isinstance(request.data, dict) else None
        errors = validate_add_text_ops(ops, session.page_meta or [])
        if errors:
            return Response({"status": "error", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        session.ops = ops
        session.save(update_fields=["ops", "updated_at"])
        return Response({"status": "success", "data": _session_payload(session)})

    def delete(self, request, pk):
        document = _owned_document(request, pk)
        if document is None:
            return _not_found()
        session = _open_session(document, request.user)
        if session is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        session.status = DocumentEditSession.Status.DISCARDED
        session.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentTextEditCommitView(APIView):
    """Bake the posted operations into a new PDF and point the document at it."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        document = _owned_document(request, pk)
        if document is None:
            return _not_found()
        session = _open_session(document, request.user)
        if session is None:
            return _not_found()
        if _base_changed(session, document):
            return _error("base_changed", status.HTTP_409_CONFLICT)
        try:
            inspection = assert_document_editable(document)
        except PdfEditError as exc:
            return _error(exc.reason, exc.status_code, exc.extra)

        ops = request.data.get("ops") if isinstance(request.data, dict) else None
        errors = validate_add_text_ops(ops, inspection["pages"])
        if errors:
            return Response({"status": "error", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        if not drawable_ops(ops):
            session.ops = ops
            session.status = DocumentEditSession.Status.COMMITTED
            session.save(update_fields=["ops", "status", "updated_at"])
            return Response(
                {
                    "status": "success",
                    "data": {
                        "document_id": str(document.id),
                        "file_url": document.file_url,
                        "file_size": document.file_size,
                        "revision_id": None,
                        "session_id": str(session.id),
                    },
                }
            )

        source = None
        new_url = None
        try:
            source = download_pdf_to_temp(session.base_file_url)
            with temp_pdf_file() as dest:
                apply_add_text(str(source), str(dest), ops)
                file_size = dest.stat().st_size
                new_url = upload_text_edit_pdf(document.id, session.id, dest)
            with transaction.atomic():
                revision = DocumentRevision.objects.create(
                    document=document,
                    file_url=new_url,
                    file_size=file_size,
                    source="add_text",
                    session=session,
                )
                document.file_url = new_url
                document.file_size = file_size
                document.save(update_fields=["file_url", "file_size", "updated_at"])
                session.ops = ops
                session.page_meta = inspection["pages"]
                session.status = DocumentEditSession.Status.COMMITTED
                session.save(update_fields=["ops", "page_meta", "status", "updated_at"])
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

        return Response(
            {
                "status": "success",
                "data": {
                    "document_id": str(document.id),
                    "file_url": document.file_url,
                    "file_size": document.file_size,
                    "revision_id": str(revision.id),
                    "session_id": str(session.id),
                },
            }
        )
