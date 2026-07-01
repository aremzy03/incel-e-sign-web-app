"""
Worker-side signing helpers that use S3 download/upload around PDF embedding.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from documents.services.pdf_files import (
    download_pdf_to_temp,
    next_signing_version,
    upload_signing_version,
)
from envelopes.models import EnvelopeDocument
from signatures.services.signing import embed_document_pdf_for_signer

LOGGER = logging.getLogger(__name__)


def embed_envelope_document_for_signer(
    envelope,
    signer,
    envelope_document: EnvelopeDocument,
    signature_image_data: str,
    *,
    fallback_placement: dict[str, Any] | None = None,
) -> str:
    """
    Download source PDF, embed signature/fields, upload signing version.

    Returns:
        str: New file URL for the document.

    Raises:
        Exception: On download, embed, or upload failure.
    """
    document = envelope_document.document
    source_url = document.signed_file_url or document.file_url
    input_path = download_pdf_to_temp(source_url)
    try:
        output_path = f"{input_path}.signed.pdf"
        embed_document_pdf_for_signer(
            envelope,
            signer,
            envelope_document,
            str(input_path),
            output_path,
            signature_image_data,
            fallback_placement=fallback_placement,
        )
        version = next_signing_version(envelope.id, document.id)
        new_url = upload_signing_version(envelope.id, document.id, version, output_path)
        document.signed_file_url = new_url
        document.file_url = new_url
        document.save(update_fields=["signed_file_url", "file_url", "updated_at"])
        return new_url
    finally:
        for path in (str(input_path), f"{input_path}.signed.pdf"):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                LOGGER.warning("Failed to cleanup temp file %s", path)
