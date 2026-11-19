"""
Bake additive text onto a PDF in one read and one write.

The original content stream stays in the file. New words are a transparent
overlay merged once per page. This module does not call the signing pipeline.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PLACEHOLDER_TEXT = "Type your text"
MAX_TEXT_LENGTH = 2000
MAX_BOXES = 200
MAX_BOXES_PER_PAGE = 50
MIN_FONT_SIZE = 6
MAX_FONT_SIZE = 72
FRAME_TOLERANCE = 0.5
MAX_PAGES = 200
MAX_FILE_BYTES = 50 * 1024 * 1024
LINE_STEP_RATIO = 1.2

# Where the editor's browser box puts the first baseline, as a fraction of the font size
# below the box top. CSS centres the font's content area (ascent + descent) in each 1.2
# line, so the baseline sits at half the leftover leading plus the ascent. The editor
# renders with Arial / Times New Roman / Courier New (or Liberation Sans / Serif / Mono),
# which share these vertical metrics (hhea, per 1 em) on every platform:
#   sans   ascent 0.9053, descent 0.2119
#   serif  ascent 0.8911, descent 0.2163
#   mono   ascent 0.8325, descent 0.3003
# A single ratio (0.8) drew text about 0.15 em higher than the editor showed it.
def _first_baseline_ratio(ascent: float, descent: float) -> float:
    return (LINE_STEP_RATIO - (ascent + descent)) / 2 + ascent


BASELINE_RATIOS = {
    "Helvetica": _first_baseline_ratio(0.9053, 0.2119),
    "Times-Roman": _first_baseline_ratio(0.8911, 0.2163),
    "Courier": _first_baseline_ratio(0.8325, 0.3003),
}
BASELINE_RATIO = BASELINE_RATIOS["Helvetica"]

FONT_FACES = {
    ("Helvetica", False, False): "Helvetica",
    ("Helvetica", True, False): "Helvetica-Bold",
    ("Helvetica", False, True): "Helvetica-Oblique",
    ("Helvetica", True, True): "Helvetica-BoldOblique",
    ("Times-Roman", False, False): "Times-Roman",
    ("Times-Roman", True, False): "Times-Bold",
    ("Times-Roman", False, True): "Times-Italic",
    ("Times-Roman", True, True): "Times-BoldItalic",
    ("Courier", False, False): "Courier",
    ("Courier", True, False): "Courier-Bold",
    ("Courier", False, True): "Courier-Oblique",
    ("Courier", True, True): "Courier-BoldOblique",
}

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass
class PdfEditError(Exception):
    reason: str
    status_code: int = 409
    extra: dict = field(default_factory=dict)

    def as_payload(self) -> dict:
        payload = {"status": "error", "reason": self.reason}
        payload.update(self.extra)
        return payload


def text_is_drawable(text: str) -> bool:
    """
    True when every character is in the standard PDF WinAnsi set.

    Newlines are layout, not glyphs. Code points above 255 and characters
    cp1252 cannot encode are rejected. Latin-1 letters such as é are allowed
    because Helvetica can draw them.
    """
    sample = text.replace("\n", "").replace("\t", "")
    if any(ord(ch) > 255 for ch in sample):
        return False
    try:
        sample.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def reportlab_font_name(font: str, bold: bool, italic: bool) -> str | None:
    return FONT_FACES.get((font, bool(bold), bool(italic)))


def _parse_color(value: str) -> Color:
    hex_value = value[1:]
    red = int(hex_value[0:2], 16) / 255
    green = int(hex_value[2:4], 16) / 255
    blue = int(hex_value[4:6], 16) / 255
    return Color(red, green, blue)


def _wrap_paragraph(text: str, font_name: str, font_size: float, width: float) -> list[str]:
    if text == "":
        return [""]
    if width <= 0:
        return [text]
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= width + 0.01:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if stringWidth(word, font_name, font_size) <= width + 0.01:
            current = word
            continue
        chunk = ""
        for char in word:
            trial = chunk + char
            if stringWidth(trial, font_name, font_size) <= width + 0.01:
                chunk = trial
            else:
                if chunk:
                    lines.append(chunk)
                chunk = char
        current = chunk
    if current or not lines:
        lines.append(current)
    return lines


def _line_draw_x(align: str, x: float, width: float, line: str, font_name: str, font_size: float) -> float:
    measured = stringWidth(line, font_name, font_size) if line else 0
    if align == "center":
        return x + (width - measured) / 2
    if align == "right":
        return x + width - measured
    return x


def validate_add_text_ops(ops: list, pages: list[dict]) -> list[dict]:
    """Return a list of {opId, reason} errors. An empty list means the ops are usable."""
    errors: list[dict] = []
    if not isinstance(ops, list):
        return [{"opId": None, "reason": "invalid_ops"}]
    if len(ops) > MAX_BOXES:
        errors.append({"opId": None, "reason": "too_many_boxes"})
    pages_by_number = {int(page["page"]): page for page in pages}
    per_page: dict[int, int] = {}
    for raw in ops:
        op_id = raw.get("opId") if isinstance(raw, dict) else None
        if not isinstance(raw, dict):
            errors.append({"opId": op_id, "reason": "invalid_op"})
            continue
        if raw.get("op") != "add_text":
            errors.append({"opId": op_id, "reason": "unknown_op"})
            continue
        try:
            page_number = int(raw.get("page"))
            x = float(raw.get("x"))
            y = float(raw.get("y"))
            width = float(raw.get("width"))
            height = float(raw.get("height"))
            font_size = float(raw.get("fontSize"))
        except (TypeError, ValueError):
            errors.append({"opId": op_id, "reason": "invalid_op"})
            continue
        text = raw.get("text")
        if not isinstance(text, str):
            errors.append({"opId": op_id, "reason": "invalid_op"})
            continue
        if len(text) > MAX_TEXT_LENGTH:
            errors.append({"opId": op_id, "reason": "text_too_long"})
        font = raw.get("font")
        if reportlab_font_name(font, raw.get("bold"), raw.get("italic")) is None:
            errors.append({"opId": op_id, "reason": "invalid_font"})
        if raw.get("align") not in ("left", "center", "right"):
            errors.append({"opId": op_id, "reason": "invalid_align"})
        color = raw.get("color")
        if not isinstance(color, str) or not _COLOR_RE.match(color):
            errors.append({"opId": op_id, "reason": "invalid_color"})
        if font_size < MIN_FONT_SIZE or font_size > MAX_FONT_SIZE:
            errors.append({"opId": op_id, "reason": "font_size"})
        page = pages_by_number.get(page_number)
        if page is None:
            errors.append({"opId": op_id, "reason": "page_out_of_range"})
        else:
            per_page[page_number] = per_page.get(page_number, 0) + 1
            page_width = float(page["width"])
            page_height = float(page["height"])
            if (
                x < -FRAME_TOLERANCE
                or y < -FRAME_TOLERANCE
                or x + width > page_width + FRAME_TOLERANCE
                or y + height > page_height + FRAME_TOLERANCE
                or width <= 0
                or height <= 0
            ):
                errors.append({"opId": op_id, "reason": "off_page"})
        if text and text != PLACEHOLDER_TEXT and not text_is_drawable(text):
            errors.append({"opId": op_id, "reason": "unsupported_character"})
    for page_number, count in per_page.items():
        if count > MAX_BOXES_PER_PAGE:
            errors.append({"opId": None, "reason": "too_many_boxes", "page": page_number})
    return errors


def drawable_ops(ops: list[dict]) -> list[dict]:
    """Drop blanks and the unedited placeholder. Those boxes are not written."""
    kept = []
    for op in ops:
        text = op.get("text") or ""
        if not str(text).strip() or text == PLACEHOLDER_TEXT:
            continue
        kept.append(op)
    return kept


def inspect_pdf(path: str) -> dict:
    """
    Open a PDF and return page sizes.

    Raises PdfEditError for encrypted, rotated, unreadable, or oversized files.
    """
    try:
        reader = PdfReader(path)
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfEditError("unreadable_pdf", 422) from exc
    if reader.is_encrypted:
        raise PdfEditError("encrypted", 409)
    pages = []
    rotated = []
    try:
        page_list = list(reader.pages)
    except Exception as exc:
        raise PdfEditError("unreadable_pdf", 422) from exc
    for index, page in enumerate(page_list, start=1):
        rotation = int(page.rotation or 0) % 360
        if rotation != 0:
            rotated.append(index)
        box = page.mediabox
        pages.append(
            {
                "page": index,
                "width": float(box.width),
                "height": float(box.height),
                "rotate": rotation,
            }
        )
    if rotated:
        raise PdfEditError("rotated_pages", 409, {"pages": rotated})
    if len(pages) > MAX_PAGES:
        raise PdfEditError("too_large", 413)
    return {"page_count": len(pages), "pages": pages}


def _draw_op(pdf_canvas, op: dict, page_width: float, page_height: float) -> None:
    font_name = reportlab_font_name(op["font"], op.get("bold"), op.get("italic"))
    if not font_name:
        return
    font_size = float(op["fontSize"])
    x = float(op["x"])
    y = float(op["y"])
    width = float(op["width"])
    height = float(op["height"])
    pdf_canvas.setFont(font_name, font_size)
    pdf_canvas.setFillColor(_parse_color(op["color"]))
    baseline_ratio = BASELINE_RATIOS.get(op["font"], BASELINE_RATIO)
    paragraphs = str(op["text"]).split("\n")
    line_index = 0
    for paragraph in paragraphs:
        for line in _wrap_paragraph(paragraph, font_name, font_size, width):
            baseline_from_top = y + (font_size * baseline_ratio) + line_index * (font_size * LINE_STEP_RATIO)
            line_index += 1
            if baseline_from_top > y + height + 0.01:
                return
            if not line:
                continue
            draw_x = _line_draw_x(op.get("align") or "left", x, width, line, font_name, font_size)
            pdf_y = page_height - baseline_from_top
            pdf_canvas.drawString(draw_x, pdf_y, line)


def apply_add_text(source_path: str, dest_path: str, ops: list[dict]) -> None:
    """
    Read source_path once. For each page that has ops, build one ReportLab
    overlay the size of that page's MediaBox and merge it. Write dest_path.
    Does not modify source_path.
    """
    if not os.path.isabs(source_path):
        raise ValueError("source_path must be an absolute path")
    if not os.path.isabs(dest_path):
        raise ValueError("dest_path must be an absolute path")

    drawable = drawable_ops(ops)
    grouped: dict[int, list[dict]] = {}
    for op in drawable:
        grouped.setdefault(int(op["page"]), []).append(op)

    with PdfReader(source_path) as reader:
        writer = PdfWriter()
        writer.clone_reader_document_root(reader)
        for index, page in enumerate(writer.pages):
            page_ops = grouped.get(index + 1)
            if not page_ops:
                continue
            box = page.mediabox
            page_width = float(box.width)
            page_height = float(box.height)
            buffer = io.BytesIO()
            pdf_canvas = canvas.Canvas(buffer, pagesize=(page_width, page_height))
            for op in page_ops:
                _draw_op(pdf_canvas, op, page_width, page_height)
            pdf_canvas.save()
            buffer.seek(0)
            overlay = PdfReader(buffer)
            page.merge_page(overlay.pages[0])

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as handle:
        writer.write(handle)


# --- Sessions with both op types (plan: docs/plan-full-text-rewrite.md) --------


def validate_text_session_ops(ops: list, pages: list[dict], *, allow_rewrite: bool) -> list[dict]:
    """
    Validate a session's ops: `add_text` (this module) and `edit_text`
    (documents.services.pdf_rewrite). `edit_text` is refused when the rewrite
    engine isn't available.
    """
    if not isinstance(ops, list):
        return [{"opId": None, "reason": "invalid_ops"}]
    adds, edits, errors = [], [], []
    for raw in ops:
        kind = raw.get("op") if isinstance(raw, dict) else None
        if kind == "edit_text":
            edits.append(raw)
        elif kind == "add_text" or not isinstance(raw, dict):
            adds.append(raw)
        else:
            errors.append({"opId": raw.get("opId"), "reason": "unknown_op"})
    errors.extend(validate_add_text_ops(adds, pages))
    if edits:
        if not allow_rewrite:
            errors.extend({"opId": raw.get("opId"), "reason": "rewrite_unavailable"} for raw in edits)
        else:
            from documents.services.pdf_rewrite import validate_edit_text_ops

            errors.extend(validate_edit_text_ops(edits, pages))
    return errors


def split_session_ops(ops: list[dict]) -> tuple[list[dict], list[dict]]:
    """(edit_text ops, drawable add_text ops). Every edit counts: empty text deletes the run."""
    edits = [op for op in ops if op.get("op") == "edit_text"]
    adds = drawable_ops([op for op in ops if op.get("op") == "add_text"])
    return edits, adds


def apply_text_session(source_path: str, dest_path: str, ops: list[dict]) -> list[dict]:
    """
    Write a session's ops into dest_path; return warnings.

    Rewrites run first (PyMuPDF deletes old glyphs, draws replacements), then
    add-text boxes are painted on top (ReportLab). The other order would let a
    redaction rectangle delete freshly added text. A session with only
    add_text ops never touches PyMuPDF, so Plan 1 output is unchanged.
    """
    import tempfile

    edits, adds = split_session_ops(ops)
    if not edits:
        apply_add_text(source_path, dest_path, adds)
        return []

    from documents.services.pdf_rewrite import rewrite_text

    if not adds:
        return rewrite_text(source_path, dest_path, edits)

    fd, middle = tempfile.mkstemp(suffix=".pdf", prefix="pdf-rewrite-")
    os.close(fd)
    try:
        warnings = rewrite_text(source_path, middle, edits)
        apply_add_text(middle, dest_path, adds)
        return warnings
    finally:
        try:
            os.remove(middle)
        except OSError:
            pass
