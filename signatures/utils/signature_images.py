"""
Size limits for saved signature images.

Signatures are often phone photos or large canvas exports. Stored at full size they are
downloaded on every sign page, fetched by the signing worker for every job and, before
the stamp downscale, embedded in every signed PDF. 800x400 is about four times the size
of a typical signature box at print resolution, so nothing visible is lost.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

MAX_SIGNATURE_SIZE = (800, 400)


def shrink_signature(image: Image.Image) -> Image.Image:
    """Return ``image`` scaled down to fit MAX_SIGNATURE_SIZE (aspect kept), or as is when it fits."""
    if image.width <= MAX_SIGNATURE_SIZE[0] and image.height <= MAX_SIGNATURE_SIZE[1]:
        return image
    resized = image.copy()
    resized.thumbnail(MAX_SIGNATURE_SIZE, Image.LANCZOS)
    return resized


def shrink_signature_png(data: bytes) -> bytes | None:
    """PNG bytes of a smaller copy, or None when the image already fits or can't be read."""
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.width <= MAX_SIGNATURE_SIZE[0] and image.height <= MAX_SIGNATURE_SIZE[1]:
                return None
            if image.mode not in ("RGB", "RGBA", "L", "LA"):
                image = image.convert("RGBA")
            out = BytesIO()
            shrink_signature(image).save(out, format="PNG", optimize=True)
    except Exception:
        return None
    return out.getvalue()
