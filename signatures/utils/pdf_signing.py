import io
import os
import base64
from typing import Tuple

from django.conf import settings

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def _decode_signature_image(signature_image: str) -> bytes:
    """
    Decode base64 signature image. Supports raw base64 or data URLs.
    """
    if not signature_image:
        raise ValueError("signature_image is empty")

    if signature_image.startswith('data:'):
        if ';base64,' not in signature_image:
            raise ValueError("Invalid data URL for signature image")
        signature_image = signature_image.split(';base64,', 1)[1]

    try:
        return base64.b64decode(signature_image, validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 signature image") from exc


def _make_signature_overlay(page_width: float, page_height: float, image_bytes: bytes, x: float, y: float, width: float, height: float) -> bytes:
    """
    Create a single-page PDF overlay with the signature image positioned at (x, y).
    Coordinates are expected in PDF points with origin at bottom-left.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    img = ImageReader(io.BytesIO(image_bytes))
    c.drawImage(img, x, y, width=width, height=height, mask='auto', preserveAspectRatio=True, anchor='sw')
    c.save()
    buffer.seek(0)
    return buffer.read()


def embed_signature(pdf_path: str, output_path: str, signature_image: str, page: int, x: float, y: float, width: float, height: float) -> None:
    """
    Embeds a signature image into a PDF file at the given page and coordinates.

    Args:
        pdf_path: Absolute path to input PDF.
        output_path: Absolute path where signed PDF will be written.
        signature_image: Base64 PNG/JPEG string, may be data URL or raw base64.
        page: 1-based page number.
        x, y: Coordinates in PDF points relative to bottom-left corner.
        width, height: Size of the signature image in points.
    """
    if not os.path.isabs(pdf_path):
        raise ValueError("pdf_path must be an absolute path")
    if not os.path.isabs(output_path):
        raise ValueError("output_path must be an absolute path")

    reader = PdfReader(pdf_path)
    if page < 1 or page > len(reader.pages):
        raise IndexError(f"page {page} is out of bounds for document with {len(reader.pages)} pages")

    image_bytes = _decode_signature_image(signature_image)

    writer = PdfWriter()

    target_index = page - 1
    for i, p in enumerate(reader.pages):
        page_obj = p
        if i == target_index:
            # determine page size
            media_box = page_obj.mediabox
            page_width = float(media_box.width)
            page_height = float(media_box.height)

            overlay_pdf_bytes = _make_signature_overlay(page_width, page_height, image_bytes, x, y, width, height)
            overlay_reader = PdfReader(io.BytesIO(overlay_pdf_bytes))
            overlay_page = overlay_reader.pages[0]
            page_obj.merge_page(overlay_page)

        writer.add_page(page_obj)

    # Ensure destination directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        writer.write(f)


def get_media_absolute_path_from_url(file_url: str) -> str:
    """
    Convert a MEDIA_URL-based URL (e.g. /media/documents/file.pdf) to an absolute file system path under MEDIA_ROOT.
    """
    if not file_url:
        raise ValueError("file_url is empty")
    media_url = settings.MEDIA_URL
    if not file_url.startswith(media_url):
        # If already absolute path or other storage, return as-is
        return file_url
    relative_path = file_url[len(media_url):]
    return os.path.join(str(settings.MEDIA_ROOT), relative_path)



