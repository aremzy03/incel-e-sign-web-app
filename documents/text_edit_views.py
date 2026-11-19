"""
Draft additive-text sessions.

The client sends operations. The server opens the stored PDF and bakes them.
Pending envelopes and non-draft documents are refused here. Recipient typing
uses a separate signing endpoint.
"""

from __future__ import annotations

import os

from django.db import transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
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
from documents.services.pdf_rewrite import (
    RewriteError,
    extract_preview_font,
    page_rules,
    page_text_styles,
    pymupdf_available,
)
from documents.services.pdf_text import (
    MAX_FILE_BYTES,
    PdfEditError,
    apply_text_session,
    inspect_pdf,
    split_session_ops,
    validate_text_session_ops,
)

# Run hit targets the editor may build per page, and the smallest editable text (plan §6.1, §12).
REWRITE_LIMITS = {"max_runs_per_page": 2000, "min_font_size": 4}

EDIT_COPY = {
    "not_draft": "Only draft documents can be edited.",
    "pending_envelope": "This document is in an envelope that’s still out for signature.",
    "rotated_pages": "This PDF’s pages are rotated. Rotate it upright before adding text.",
    "encrypted": "This PDF is protected and can’t be edited.",
    "unreadable_pdf": "This file couldn’t be opened as a PDF.",
    "base_changed": "This document was updated. Your text was not applied.",
    "unsupported_character": "This font can’t draw one of the characters in a text box.",
    "too_large": "This document is too large to edit here (limit 200 pages or 50 MB).",
    "rewrite_failed": "Couldn’t replace the text on the page. The file was not changed.",
    "box_covers_other_text": "This edit would remove text on another line. Undo it and pick the word again.",
    "rotated_text": "Rotated text can’t be edited.",
    "invalid_fit": "An edit’s layout is invalid. Undo it and edit the text again.",
    "session_closed": "This editing session was closed (saved or discarded elsewhere). Reopen the document to keep editing.",
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


def _assert_editable_state(document: Document) -> None:
    """The guards that need no file: status, envelope and size."""
    if document.status != "draft":
        raise PdfEditError("not_draft", status.HTTP_409_CONFLICT)
    from envelopes.models import EnvelopeDocument

    if EnvelopeDocument.objects.filter(document=document, envelope__status="pending").exists():
        raise PdfEditError("pending_envelope", status.HTTP_409_CONFLICT)
    if (document.file_size or 0) > MAX_FILE_BYTES:
        raise PdfEditError("too_large", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


def assert_document_editable(document: Document, *, local_path=None, read_layout: bool = True) -> dict:
    """
    Guards shared by every draft text-edit route, then the file's page sizes.

    The caller has already restricted the document to its owner. Pass ``local_path``
    when the caller already has the file (it is then left for the caller to delete).
    ``read_layout`` adds the editor's preview data (styles, borders); saving skips it.
    """
    _assert_editable_state(document)
    owns_file = local_path is None
    try:
        if owns_file:
            local_path = download_pdf_to_temp(document.file_url)
        inspection = inspect_pdf(str(local_path))
        if read_layout and pymupdf_available():
            # Colours and bold/italic for the editor's preview, read while the file is
            # already here (about 2 ms a page). Best effort: the save reads them again.
            try:
                inspection["text_styles"] = page_text_styles(str(local_path))
            except Exception:
                inspection["text_styles"] = None
            # Borders and boxes, so long edits can be fitted inside them.
            try:
                inspection["text_rules"] = page_rules(str(local_path))
            except Exception:
                inspection["text_rules"] = None
        return inspection
    except FileNotFoundError as exc:
        raise PdfEditError("unreadable_pdf", status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
    finally:
        if owns_file and local_path is not None:
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
        # False when PyMuPDF isn't installed: the editor then offers add-text only.
        "rewrite": pymupdf_available(),
        "limits": REWRITE_LIMITS,
        # Only when the file was just inspected (opening the session), not on autosave.
        **({"text_styles": inspection.get("text_styles"), "text_rules": inspection.get("text_rules")} if inspection else {}),
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


# Compressed: the session carries every page's styles and borders, and fonts are
# hundreds of KB. These responses hold no secrets, so compression is safe here.
@method_decorator(gzip_page, name="dispatch")
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
            # The document exists but has no open session: it was saved or discarded
            # (another tab, or a reopen after saving failed). Distinct from "no such document"
            # so the editor can open a new session and keep the user's work.
            return _error("session_closed", status.HTTP_409_CONFLICT)
        if _base_changed(session, document):
            return _error("base_changed", status.HTTP_409_CONFLICT)
        ops = request.data.get("ops") if isinstance(request.data, dict) else None
        errors = validate_text_session_ops(ops, session.page_meta or [], allow_rewrite=pymupdf_available())
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
            return _error("session_closed", status.HTTP_409_CONFLICT)
        if _base_changed(session, document):
            return _error("base_changed", status.HTTP_409_CONFLICT)
        # One download: it is checked, then rewritten. The session's base is the current
        # file (checked above), and a cached copy costs only a HEAD request.
        source = None
        try:
            try:
                _assert_editable_state(document)
                source = download_pdf_to_temp(session.base_file_url)
                inspection = assert_document_editable(document, local_path=source, read_layout=False)
            except FileNotFoundError:
                return _error("unreadable_pdf", status.HTTP_422_UNPROCESSABLE_ENTITY)
            except PdfEditError as exc:
                return _error(exc.reason, exc.status_code, exc.extra)

            ops = request.data.get("ops") if isinstance(request.data, dict) else None
            errors = validate_text_session_ops(ops, inspection["pages"], allow_rewrite=pymupdf_available())
            if errors:
                return Response({"status": "error", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            edits, adds = split_session_ops(ops)
            if not edits and not adds:
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
                            "warnings": [],
                        },
                    }
                )

            new_url = None
            warnings: list[dict] = []
            try:
                with temp_pdf_file() as dest:
                    try:
                        warnings = apply_text_session(str(source), str(dest), ops)
                    except RewriteError as exc:
                        # Nothing was uploaded; the document and the open session are untouched.
                        return _error(exc.reason, exc.status_code, {"opIds": exc.op_ids})
                    file_size = dest.stat().st_size
                    # The upload also leaves a local copy, so reopening the session doesn't download it.
                    new_url = upload_text_edit_pdf(document.id, session.id, dest)
                with transaction.atomic():
                    revision = DocumentRevision.objects.create(
                        document=document,
                        file_url=new_url,
                        file_size=file_size,
                        source="edit_text" if edits else "add_text",
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
                    "warnings": warnings,
                },
            }
        )


# Compressed: the session carries every page's styles and borders, and fonts are
# hundreds of KB. These responses hold no secrets, so compression is safe here.
@method_decorator(gzip_page, name="dispatch")
class DocumentTextEditFontView(APIView):
    """
    One embedded font program from the document's current file, so the editor can
    preview typed text in the PDF's own font. Ids come from the session's text_styles.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, xref):
        document = _owned_document(request, pk)
        if document is None or not pymupdf_available():
            return _not_found()
        local_path = None
        try:
            local_path = download_pdf_to_temp(document.file_url)
            font = extract_preview_font(str(local_path), xref)
        except FileNotFoundError:
            font = None
        finally:
            if local_path is not None:
                try:
                    os.remove(local_path)
                except OSError:
                    pass
        if font is None:
            return _not_found()
        data, content_type = font
        response = HttpResponse(data, content_type=content_type)
        # The editor asks with ?v=<file version>; a saved edit changes the file and the ids.
        response["Cache-Control"] = "private, max-age=86400"
        return response
