"""
PDF security utilities for envelopes.

Provides helpers to apply password-based locking to signed PDFs.
"""

import logging
import os
from typing import Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def lock_pdf_with_password(
    *,
    pdf_path: str,
    password: str,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Apply password protection to a PDF, returning the path to the locked copy.

    Args:
        pdf_path (str): Absolute path to the source PDF.
        password (str): Password to apply to the PDF (used as both user and owner password).
        output_path (Optional[str]): Optional absolute path for the locked PDF.

    Returns:
        Optional[str]: Absolute path to the locked PDF or None if locking failed.

    Raises:
        ValueError: If pdf_path/output_path are not absolute paths or password is empty.
    """
    if not password:
        raise ValueError("password must be a non-empty string")

    if not pdf_path or not os.path.isabs(pdf_path):
        raise ValueError("pdf_path must be an absolute path")

    if output_path is not None and not os.path.isabs(output_path):
        raise ValueError("output_path must be an absolute path when provided")

    if not os.path.exists(pdf_path):
        logger.warning("lock_pdf_with_password: file not found: %s", pdf_path)
        return None

    try:
        with PdfReader(pdf_path) as reader:
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            # Use the same password for user and owner for simplicity.
            writer.encrypt(user_password=password, owner_password=password)
    except Exception as exc:
        logger.error("lock_pdf_with_password: failed to encrypt PDF %s: %s", pdf_path, exc)
        return None

    locked_path = output_path
    if locked_path is None:
        base, ext = os.path.splitext(pdf_path)
        locked_path = f"{base}_locked{ext or '.pdf'}"

    try:
        os.makedirs(os.path.dirname(locked_path), exist_ok=True)
        with open(locked_path, "wb") as locked_file:
            writer.write(locked_file)
    except Exception as exc:
        logger.error("lock_pdf_with_password: failed to write locked PDF %s -> %s: %s", pdf_path, locked_path, exc)
        return None

    return locked_path


