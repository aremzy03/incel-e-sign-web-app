"""
Utility functions for the documents app.

This module currently provides helpers for converting Word documents to PDF
using a headless LibreOffice process.
"""

import os
import shutil
import subprocess
from typing import Optional

from django.conf import settings


def ensure_dir(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def get_absolute_media_path(relative_path: str) -> str:
    """
    Given a storage relative path (e.g., documents/file.pdf), return absolute
    path under MEDIA_ROOT. If the provided path is already absolute, return it.
    """
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(str(settings.MEDIA_ROOT), relative_path)


def convert_word_to_pdf(input_abs_path: str, output_dir_abs: str) -> str:
    """
    Convert a Word document (.doc or .docx) to PDF using LibreOffice (soffice).

    Args:
        input_abs_path: Absolute path to the source .doc/.docx file.
        output_dir_abs: Absolute directory where the PDF should be written.

    Returns:
        Absolute path to the generated PDF file.

    Raises:
        RuntimeError: If conversion fails or output file is not produced.
    """
    if not os.path.isabs(input_abs_path):
        raise ValueError("input_abs_path must be absolute")
    if not os.path.isabs(output_dir_abs):
        raise ValueError("output_dir_abs must be absolute")

    ensure_dir(output_dir_abs)

    # Ensure LibreOffice (soffice) is available
    if shutil.which("soffice") is None:
        raise RuntimeError(
            "LibreOffice is not installed or 'soffice' is not on PATH. "
            "Please install LibreOffice and ensure 'soffice' is available."
        )

    # Run LibreOffice in headless mode to convert to PDF
    # Note: Requires LibreOffice to be installed and available as `soffice`.
    try:
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                output_dir_abs,
                input_abs_path,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        # 'soffice' command not found
        raise RuntimeError(
            "LibreOffice (soffice) executable not found. Install LibreOffice and add it to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"LibreOffice conversion failed: {exc.stderr.decode(errors='ignore')}"
        ) from exc

    # LibreOffice writes a PDF with the same base name in output_dir_abs
    base_name = os.path.splitext(os.path.basename(input_abs_path))[0]
    output_pdf_abs = os.path.join(output_dir_abs, f"{base_name}.pdf")

    if not os.path.exists(output_pdf_abs):
        raise RuntimeError("PDF conversion did not produce an output file")

    return output_pdf_abs


