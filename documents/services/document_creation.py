"""
Helpers for durable document creation after staging upload succeeds.
"""

from __future__ import annotations

from pathlib import Path
import uuid

from documents.models import Document
from documents.services.pdf_files import delete_storage_url, temp_pdf_file, upload_staging_pdf


def create_draft_document_from_local_pdf(
    *,
    owner,
    file_name: str,
    local_path: str | Path,
    file_size: int | None = None,
    document_id: uuid.UUID | None = None,
) -> Document:
    """
    Upload a PDF to staging and create the Document row only after upload succeeds.

    If database persistence fails after the upload, the staged object is deleted
    so the system does not leak orphaned storage artifacts.
    """
    resolved_document_id = document_id or uuid.uuid4()
    resolved_local_path = Path(local_path)
    resolved_file_size = file_size if file_size is not None else resolved_local_path.stat().st_size

    file_url = upload_staging_pdf(resolved_document_id, resolved_local_path)
    try:
        return Document.objects.create(
            id=resolved_document_id,
            owner=owner,
            file_url=file_url,
            file_name=file_name,
            file_size=resolved_file_size,
            status="draft",
        )
    except Exception:
        delete_storage_url(file_url)
        raise


def create_draft_document_from_pdf_bytes(
    *,
    owner,
    file_name: str,
    pdf_bytes: bytes,
    document_id: uuid.UUID | None = None,
) -> Document:
    """Persist PDF bytes to staging storage before creating the Document row."""
    with temp_pdf_file() as temp_path:
        temp_path.write_bytes(pdf_bytes)
        return create_draft_document_from_local_pdf(
            owner=owner,
            file_name=file_name,
            local_path=temp_path,
            file_size=len(pdf_bytes),
            document_id=document_id,
        )
