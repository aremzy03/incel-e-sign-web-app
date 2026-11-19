"""
Replace words that are already in a PDF (plan: docs/plan-full-text-rewrite.md).

`edit_text` ops name an existing text run: the tight glyph box to remove
(`remove`, PDF user space, bottom-left origin) and the baseline to draw the
replacement at. PyMuPDF deletes the text operators inside each box
(`apply_redactions`, text only, images and vector art kept), draws the
replacement with a real font file, and saves with `garbage=4` so the old glyph
data is gone from the file, not just hidden. The output is then checked
before the caller may swap the document's file.

PyMuPDF (AGPL-3.0) is accepted for this internal, open-source app. It is
imported lazily so Django start-up does not pay for it.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field

from documents.services.text_fit import fit_text, validate_fit

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

MAX_EDITS = 200
MAX_TEXT_LENGTH = 2000
MIN_FONT_SIZE = 1.0
MAX_FONT_SIZE = 400.0
# The remove box is a glyph box; one taller than this is a client bug (plan §5.2).
MAX_REMOVE_HEIGHT_FACTOR = 4.0
PAGE_TOLERANCE = 1.0
# A character "falls inside" a remove box when its centre is inside the box grown by this (plan §10).
VERIFY_SLACK = 1.0
# Characters inside the box whose baseline is further than this from the run's are another line.
OTHER_LINE_FACTOR = 0.5

FALLBACK_FONTS = ("LiberationSans", "LiberationSerif", "LiberationMono")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")

# Standard-14 PDF fonts are named, never embedded; their Liberation twins are metric-compatible.
_STANDARD_FONT_FAMILIES = {
    "helvetica": "LiberationSans",
    "arial": "LiberationSans",
    "times": "LiberationSerif",
    "courier": "LiberationMono",
}


@dataclass
class RewriteError(Exception):
    reason: str
    status_code: int = 422
    op_ids: list = field(default_factory=list)

    def as_payload(self) -> dict:
        return {"status": "error", "reason": self.reason, "opIds": self.op_ids}


def pymupdf_available() -> bool:
    try:
        import fitz  # noqa: F401
    except Exception:
        return False
    return True


# --- Validation (no file access) ---------------------------------------------


def _number(value) -> float:
    if isinstance(value, bool):
        raise TypeError("bool is not a number")
    return float(value)


def validate_edit_text_ops(ops: list, pages: list[dict]) -> list[dict]:
    """Return {opId, reason} errors for `edit_text` ops. Empty means usable."""
    errors: list[dict] = []
    if len(ops) > MAX_EDITS:
        errors.append({"opId": None, "reason": "too_many_edits"})
    pages_by_number = {int(page["page"]): page for page in pages}
    by_page: dict[int, list[tuple[str, tuple[float, float, float, float]]]] = {}

    for raw in ops:
        op_id = raw.get("opId")
        try:
            page_number = int(raw.get("page"))
            font_size = _number(raw.get("fontSize"))
            baseline = raw.get("baseline") or {}
            bx, by = _number(baseline.get("x")), _number(baseline.get("y"))
            remove = raw.get("remove") or {}
            rx, ry = _number(remove.get("x")), _number(remove.get("y"))
            rw, rh = _number(remove.get("width")), _number(remove.get("height"))
        except (TypeError, ValueError, AttributeError):
            errors.append({"opId": op_id, "reason": "invalid_op"})
            continue

        text = raw.get("text")
        original = raw.get("originalText")
        if not isinstance(op_id, str) or not op_id or not isinstance(text, str) or not isinstance(original, str):
            errors.append({"opId": op_id, "reason": "invalid_op"})
            continue
        if len(text) > MAX_TEXT_LENGTH:
            errors.append({"opId": op_id, "reason": "text_too_long"})
        color = raw.get("color")
        if not isinstance(color, str) or not _COLOR_RE.match(color):
            errors.append({"opId": op_id, "reason": "invalid_color"})
        if raw.get("fallbackFont") not in (None, *FALLBACK_FONTS):
            errors.append({"opId": op_id, "reason": "invalid_font"})
        if not MIN_FONT_SIZE <= font_size <= MAX_FONT_SIZE:
            errors.append({"opId": op_id, "reason": "font_size"})
        if rw <= 0 or rh <= 0 or rh > MAX_REMOVE_HEIGHT_FACTOR * font_size:
            errors.append({"opId": op_id, "reason": "invalid_box"})

        page = pages_by_number.get(page_number)
        if page is None:
            errors.append({"opId": op_id, "reason": "page_out_of_range"})
            continue
        width, height = float(page["width"]), float(page["height"])
        inside = (
            rx >= -PAGE_TOLERANCE
            and ry >= -PAGE_TOLERANCE
            and rx + rw <= width + PAGE_TOLERANCE
            and ry + rh <= height + PAGE_TOLERANCE
            and -PAGE_TOLERANCE <= bx <= width + PAGE_TOLERANCE
            and -PAGE_TOLERANCE <= by <= height + PAGE_TOLERANCE
        )
        if not inside:
            errors.append({"opId": op_id, "reason": "off_page"})
            continue
        if not validate_fit(raw.get("fit"), baseline_y=by, font_size=font_size, page_width=width,
                            page_height=height, tolerance=PAGE_TOLERANCE):
            errors.append({"opId": op_id, "reason": "invalid_fit"})
            continue
        by_page.setdefault(page_number, []).append((op_id, (rx, ry, rx + rw, ry + rh)))

    # Two rewrites deleting overlapping rectangles would fight over the same glyphs.
    for boxes in by_page.values():
        for i, (id_a, a) in enumerate(boxes):
            for id_b, b in boxes[i + 1:]:
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    errors.append({"opId": id_b, "reason": "boxes_overlap", "otherOpId": id_a})
    return errors


# --- Geometry -----------------------------------------------------------------


def _remove_rect(page, edit: dict):
    """The op's bottom-left `remove` box as a PyMuPDF (top-left) rect, honouring the MediaBox origin."""
    import fitz

    box = edit["remove"]
    x0, y0 = float(box["x"]), float(box["y"])
    rect = fitz.Rect(x0, y0, x0 + float(box["width"]), y0 + float(box["height"])) * page.transformation_matrix
    rect.normalize()
    return rect


def _baseline_point(page, edit: dict):
    baseline = edit["baseline"]
    return _user_point(page, float(baseline["x"]), float(baseline["y"]))


def _user_point(page, x: float, y: float):
    """A PDF user-space point (bottom-left origin) as a PyMuPDF point."""
    import fitz

    return fitz.Point(x, y) * page.transformation_matrix


def _line_rect(page, x: float, y: float, width: float, size: float):
    """PyMuPDF rect of one drawn line: from its descenders to its cap height."""
    import fitz

    rect = fitz.Rect(x, y - 0.25 * size, x + width, y + 0.75 * size) * page.transformation_matrix
    rect.normalize()
    return rect


def _page_chars(page) -> list[dict]:
    """Every character on the page with its bbox centre, baseline y and line direction."""
    chars = []
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            direction = line.get("dir", (1, 0))
            for span in line.get("spans", []):
                font = span.get("font", "")
                color = span.get("color", 0)
                flags = span.get("flags", 0)
                for char in span.get("chars", []):
                    x0, y0, x1, y1 = char["bbox"]
                    chars.append(
                        {
                            "c": char["c"],
                            "cx": (x0 + x1) / 2,
                            "cy": (y0 + y1) / 2,
                            "origin_y": char["origin"][1],
                            "font": font,
                            "color": color,
                            "flags": flags,
                            "horizontal": abs(direction[1]) < 0.01 and direction[0] > 0,
                        }
                    )
    return chars


def _chars_in(chars: list[dict], rect, slack: float = 0.0) -> list[dict]:
    return [
        ch
        for ch in chars
        if rect.x0 - slack <= ch["cx"] <= rect.x1 + slack and rect.y0 - slack <= ch["cy"] <= rect.y1 + slack
    ]


def _squash(text: str) -> str:
    return "".join(text.split())


# --- Fonts ----------------------------------------------------------------------


def _base_font_name(name: str) -> str:
    return _SUBSET_PREFIX.sub("", name or "")


def classify_font(font_name: str) -> str:
    """Liberation family for a font name (plan §7.2): serif, mono, else sans."""
    name = _base_font_name(font_name).lower()
    if any(key in name for key in ("times", "georgia", "cambria", "garamond", "liberation serif", "serif")):
        if "sans" not in name:
            return "LiberationSerif"
    if any(key in name for key in ("courier", "consolas", "mono", "typewriter")):
        return "LiberationMono"
    return "LiberationSans"


def _style_suffix(font_name: str, bold: bool | None = None, italic: bool | None = None) -> str:
    """Liberation style for a run. Explicit flags (read from the PDF) win over the font name."""
    name = (font_name or "").lower()
    if bold is None:
        bold = "bold" in name or "black" in name or "heavy" in name
    if italic is None:
        italic = "italic" in name or "oblique" in name
    return {(True, True): "BoldItalic", (True, False): "Bold", (False, True): "Italic"}.get((bold, italic), "Regular")


def liberation_path(family: str, font_name: str = "", bold: bool | None = None, italic: bool | None = None) -> tuple[str, bool]:
    """Path to the Liberation file for a family and the run's style. True when the style had to fall back to Regular."""
    style = _style_suffix(font_name, bold, italic)
    path = os.path.join(FONT_DIR, f"{family}-{style}.ttf")
    if os.path.exists(path):
        return path, False
    return os.path.join(FONT_DIR, f"{family}-Regular.ttf"), style != "Regular"


def _font_key(name: str) -> str:
    """Comparable font name: no subset prefix, case, spaces, hyphens or underscores."""
    key = re.sub(r"[\s\-_,]", "", _base_font_name(name or "")).lower()
    # "Liberation Serif Regular" and "Liberation Serif" are the same face.
    return key[: -len("regular")] if key.endswith("regular") and len(key) > len("regular") else key


def _embedded_font_key(doc, xref: int, ext) -> str | None:
    """_font_key of the real name inside an embedded font program, or None."""
    import fitz

    if ext in ("n/a", "", None):
        return None
    try:
        buffer = doc.extract_font(xref)[3]
        return _font_key(fitz.Font(fontbuffer=buffer).name) if buffer else None
    except Exception:
        return None


def _drawable_chars(text: str) -> set[int]:
    return {ord(ch) for ch in text if not ch.isspace()}


def resolve_font(doc, page, edit: dict, tmpdir: str) -> tuple[str, str, dict | None]:
    """
    `_pick_font`, refusing a font that can't draw every character: inserting with it
    would put empty .notdef boxes in the file (plan §18).
    """
    import fitz

    fontfile, fontname, warning = _pick_font(doc, page, edit, tmpdir)
    needed = _drawable_chars(edit["text"])
    if needed and not needed <= set(fitz.Font(fontfile=fontfile).valid_codepoints()):
        raise RewriteError("unsupported_character", 400, [edit["opId"]])
    return fontfile, fontname, warning


def _pick_font(doc, page, edit: dict, tmpdir: str) -> tuple[str, str, dict | None]:
    """
    Pick the font file for a replacement. Returns (fontfile, fontname, warning).

    1. The client asked for a Liberation fallback: use it (warning font_replaced).
    2. The page embeds a font with the run's name that can draw every character: reuse it.
    3. The run's font is a standard font that was never embedded: its Liberation twin,
       no warning (nothing was embedded to keep, and the metrics match).
    4. Otherwise (including an embedded subset that lacks a character, even when it is
       called Arial or Times) the Liberation family by name, with warning font_replaced.
    """
    import fitz

    op_id = edit["opId"]
    font_name = edit.get("fontName") or ""
    text = edit["text"]

    requested = edit.get("fallbackFont")
    if requested:
        path, _ = liberation_path(requested, font_name, edit.get("_bold"), edit.get("_italic"))
        return path, f"Rw{requested}", {"opId": op_id, "code": "font_replaced", "font": requested}

    wanted = _base_font_name(font_name).lower()
    wanted_key = _font_key(font_name)
    standard = next((family for key, family in _STANDARD_FONT_FAMILIES.items() if key in wanted), None)
    embedded = False
    for xref, ext, _ftype, basefont, *_rest in page.get_fonts(full=True):
        # The editor may name the font as the PDF does ("CIDFont+F3") or by the real
        # name inside the embedded program ("Arial Black"); either identifies it.
        if not wanted_key or (_font_key(basefont) != wanted_key and _embedded_font_key(doc, xref, ext) != wanted_key):
            continue
        if ext in ("n/a", "", None):
            # Named but not embedded (standard-14 style).
            break
        embedded = True
        try:
            _name, file_ext, _type, buffer = doc.extract_font(xref)
            if not buffer:
                break
            font = fitz.Font(fontbuffer=buffer)
            if _drawable_chars(text) <= set(font.valid_codepoints()):
                path = os.path.join(tmpdir, f"embedded-{xref}.{file_ext or 'ttf'}")
                with open(path, "wb") as handle:
                    handle.write(buffer)
                return path, f"RwE{xref}", None
        except Exception:
            pass
        # Another font of the same name may have the letters: an earlier edit's small
        # subset ("Calibri", 20 glyphs) sits next to the original full font.
        continue

    if standard and not embedded:
        # Never embedded: the viewer was substituting anyway, and the twin's metrics match.
        path, style_missing = liberation_path(standard, font_name, edit.get("_bold"), edit.get("_italic"))
        return path, f"Rw{standard}", (
            {"opId": op_id, "code": "style_replaced", "font": standard} if style_missing else None
        )

    family = classify_font(font_name)
    path, _ = liberation_path(family, font_name, edit.get("_bold"), edit.get("_italic"))
    return path, f"Rw{family}", {"opId": op_id, "code": "font_replaced", "font": family}


def _subset_font(fontfile: str, codepoints: set[int], out_path: str) -> str:
    """
    A copy of ``fontfile`` with only the glyphs for ``codepoints``, or ``fontfile`` itself
    when that isn't possible. PyMuPDF embeds whatever file it is given: a full Liberation
    Sans is 400 KB and a reused Calibri can be 580 KB, for a few typed letters.

    Unlike PyMuPDF's own ``subset_fonts`` (which rewrites every font in the file and drops
    their character maps), this touches only the fonts the edit adds, and keeps the
    character map so the editor can preview and reuse them on a later edit.
    """
    import fitz

    try:
        import logging

        from fontTools import subset
        from fontTools.ttLib import TTFont

        # fontTools logs every table it touches at INFO, and tables it drops at WARNING.
        logging.getLogger("fontTools").setLevel(logging.ERROR)
    except ImportError:
        return fontfile
    try:
        options = subset.Options()
        options.hinting = False
        options.desubroutinize = True
        options.notdef_outline = True
        # Every name: the editor and later edits identify the font by its real name.
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        options.name_legacy = True
        # PyMuPDF doesn't shape text; kerning and ligature tables would only add bytes.
        options.layout_features = []
        options.drop_tables += ["DSIG", "GSUB", "GPOS", "GDEF", "kern"]
        font = TTFont(fontfile)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=codepoints)
        subsetter.subset(font)
        font.save(out_path)
        font.close()
        if not _drawable_chars("".join(map(chr, codepoints))) <= set(fitz.Font(fontfile=out_path).valid_codepoints()):
            return fontfile
        if os.path.getsize(out_path) >= os.path.getsize(fontfile):
            return fontfile
        return out_path
    except Exception:
        return fontfile


def _subset_page_fonts(fonts: dict, page_edits: list[dict], tmpdir: str, page_number: int) -> dict:
    """
    Subset each font the page's edits add, once per font name: PyMuPDF reuses a font name
    already on the page, so every edit using it must find its letters in the one subset.
    """
    by_name: dict[str, tuple[str, set[int]]] = {}
    for edit in page_edits:
        fontfile, fontname, _warning = fonts[edit["opId"]]
        _file, codepoints = by_name.setdefault(fontname, (fontfile, {0x20, 0xA0}))
        codepoints.update(ord(ch) for ch in edit["text"])
    subsets = {
        fontname: _subset_font(fontfile, codepoints, os.path.join(tmpdir, f"subset-p{page_number}-{fontname}.ttf"))
        for fontname, (fontfile, codepoints) in by_name.items()
    }
    return {op_id: (subsets.get(name, f), name, warning) for op_id, (f, name, warning) in fonts.items()}


# PyMuPDF span flags (TEXT_FONT_ITALIC = 2, TEXT_FONT_BOLD = 16).
_FLAG_ITALIC = 2
_FLAG_BOLD = 16


def _hex_color(value: int) -> str:
    return f"#{int(value) & 0xFFFFFF:06x}"


def _run_style(chars: list[dict]) -> dict | None:
    """The colour and bold/italic most of a run's characters are drawn with."""
    if not chars:
        return None
    from collections import Counter

    color = Counter(ch["color"] for ch in chars).most_common(1)[0][0]
    flags = Counter(ch["flags"] for ch in chars).most_common(1)[0][0]
    return {"color": _hex_color(color), "bold": bool(flags & _FLAG_BOLD), "italic": bool(flags & _FLAG_ITALIC)}


def page_text_styles(path: str) -> list[list]:
    """
    Per page, the colour and style of every text span, for the editor's preview:
    ``[x0, y0, x1, y1, "#rrggbb", bold, italic, font_name, preview_font_id]`` with the box
    in PDF user space (bottom-left origin, like pdf.js text positions). ``preview_font_id``
    names an embedded font the browser can load (see ``extract_preview_font``), or is None.
    Roughly 2 ms and 1 KB a page.
    """
    import fitz

    pages: list[list] = []
    with fitz.open(path) as doc:
        real_names: dict[str, str] = {}
        preview_ids: dict[str, str | None] = {}
        for page in doc:
            to_user = ~page.transformation_matrix
            # Generic PDF font names ("CIDFont+F3") hide the real one ("Arial Black"),
            # which is inside the embedded font program. Read it once per font.
            for xref, ext, _type, basefont, *_rest in page.get_fonts(full=True):
                if basefont in real_names:
                    continue
                real_names[basefont] = basefont
                preview_ids[basefont] = None
                try:
                    buffer = doc.extract_font(xref)[3]
                    if buffer:
                        font = fitz.Font(fontbuffer=buffer)
                        real_names[basefont] = font.name or basefont
                        if _previewable(ext, buffer, font):
                            preview_ids[basefont] = str(xref)
                except Exception:
                    pass
                # Spans may spell the name differently ("LiberationSerif" for "Liberation Serif Regular").
                real_names.setdefault(_font_key(basefont), real_names[basefont])
                preview_ids.setdefault(_font_key(basefont), preview_ids[basefont])
            spans = []
            for block in page.get_text("dict", flags=0).get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not span.get("text", "").strip():
                            continue
                        box = fitz.Rect(span["bbox"]) * to_user
                        box.normalize()
                        flags = span.get("flags", 0)
                        span_font = span.get("font", "")
                        spans.append(
                            [
                                round(box.x0, 2),
                                round(box.y0, 2),
                                round(box.x1, 2),
                                round(box.y1, 2),
                                _hex_color(span.get("color", 0)),
                                bool(flags & _FLAG_BOLD),
                                bool(flags & _FLAG_ITALIC),
                                # The real font name ("Arial Black"); the PDF may only say "CIDFont+F3".
                                real_names.get(span_font) or real_names.get(_font_key(span_font), span_font),
                                preview_ids.get(span_font) or preview_ids.get(_font_key(span_font)),
                            ]
                        )
            pages.append(spans)
    return pages


# Rules shorter than this aren't borders (bullets, dots, tick marks).
MIN_RULE_LENGTH = 4.0
# Thinner than this, a filled rectangle is a drawn line (word processors draw table borders that way).
RULE_THICKNESS = 3.0
MAX_RULES_PER_PAGE = 3000


def _is_white(color) -> bool:
    return color is not None and len(color) == 3 and all(channel > 0.98 for channel in color)


def page_rules(path: str) -> list[list]:
    """
    Per page, the straight lines that bound text, for fitting edits (plan, "Borders and alignment"):
    ``[0, x, y0, y1]`` for a vertical rule and ``[1, y, x0, x1]`` for a horizontal one, in PDF
    user space (bottom-left origin). Lines, thin filled rectangles (table borders) and the
    four edges of boxes count; invisible paths, white boxes and page-sized backgrounds don't.
    """
    import fitz

    pages: list[list] = []
    with fitz.open(path) as doc:
        for page in doc:
            to_user = ~page.transformation_matrix
            page_area = abs(page.rect)
            rules: set[tuple] = set()

            def segment(p, q):
                p, q = p * to_user, q * to_user
                if abs(p.x - q.x) < 0.5 and abs(p.y - q.y) >= MIN_RULE_LENGTH:
                    rules.add((0, round((p.x + q.x) / 2, 1), round(min(p.y, q.y), 1), round(max(p.y, q.y), 1)))
                elif abs(p.y - q.y) < 0.5 and abs(p.x - q.x) >= MIN_RULE_LENGTH:
                    rules.add((1, round((p.y + q.y) / 2, 1), round(min(p.x, q.x), 1), round(max(p.x, q.x), 1)))

            def box(rect):
                rect = fitz.Rect(rect)
                if rect.width <= RULE_THICKNESS and rect.height <= RULE_THICKNESS:
                    return
                if rect.width <= RULE_THICKNESS:
                    x = (rect.x0 + rect.x1) / 2
                    segment(fitz.Point(x, rect.y0), fitz.Point(x, rect.y1))
                elif rect.height <= RULE_THICKNESS:
                    y = (rect.y0 + rect.y1) / 2
                    segment(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y))
                elif abs(rect) < 0.8 * page_area:
                    segment(rect.tl, rect.tr)
                    segment(rect.bl, rect.br)
                    segment(rect.tl, rect.bl)
                    segment(rect.tr, rect.br)

            try:
                drawings = page.get_drawings()
            except Exception:
                drawings = []
            for drawing in drawings:
                fill, stroke = drawing.get("fill"), drawing.get("color")
                if fill is None and stroke is None:
                    continue  # a clip path: nothing is drawn
                if stroke is None and _is_white(fill):
                    continue  # a white patch on a white page
                for item in drawing.get("items", []):
                    kind = item[0]
                    if kind == "l":
                        segment(item[1], item[2])
                    elif kind == "re":
                        box(item[1])
                    elif kind == "qu" and item[1].is_rectangular:
                        box(item[1].rect)
                if len(rules) >= MAX_RULES_PER_PAGE:
                    break
            pages.append([list(rule) for rule in sorted(rules)[:MAX_RULES_PER_PAGE]])
    return pages


# Embedded fonts the editor may load into the browser for an exact preview.
# Browsers take TrueType and OpenType; bare CFF and Type 1 programs aren't loadable.
_PREVIEW_FONT_TYPES = {"ttf": "font/ttf", "otf": "font/otf"}
MAX_PREVIEW_FONT_BYTES = 4 * 1024 * 1024
_ASCII_ALNUM = [code for code in range(0x30, 0x7B) if chr(code).isalnum()]


def _previewable(ext, buffer: bytes, font) -> bool:
    """A font program the browser can load and that maps at least one ASCII letter or digit."""
    if ext not in _PREVIEW_FONT_TYPES or not buffer or len(buffer) > MAX_PREVIEW_FONT_BYTES:
        return False
    try:
        # A symbolic cmap (codes 0xF0xx) maps no Unicode letters; the browser would draw nothing with it.
        return any(font.has_glyph(code) for code in _ASCII_ALNUM)
    except Exception:
        return False


def extract_preview_font(path: str, xref: int) -> tuple[bytes, str] | None:
    """
    The embedded font program ``xref`` and its media type, when it is a font used on a
    page and the browser can load it (same test as ``page_text_styles``); else None.
    """
    import fitz

    with fitz.open(path) as doc:
        for page in doc:
            for font_xref, ext, *_rest in page.get_fonts(full=True):
                if font_xref != xref:
                    continue
                try:
                    buffer = doc.extract_font(xref)[3]
                    if buffer and _previewable(ext, buffer, fitz.Font(fontbuffer=buffer)):
                        return buffer, _PREVIEW_FONT_TYPES[ext]
                except Exception:
                    pass
                return None
    return None


def _parse_color(value: str) -> tuple[float, float, float]:
    hex_value = value[1:]
    return tuple(int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


# --- Rewrite ----------------------------------------------------------------------


def _precheck(page, edits: list[dict]) -> None:
    """Refuse boxes that would delete text the user didn't pick (plan §10), using PyMuPDF's char map."""
    chars = _page_chars(page)
    covers_other, rotated = [], []
    for edit in edits:
        rect = _remove_rect(page, edit)
        inside = _chars_in(chars, rect)
        if any(not ch["horizontal"] for ch in inside):
            rotated.append(edit["opId"])
            continue
        baseline_y = _baseline_point(page, edit).y
        limit = OTHER_LINE_FACTOR * float(edit["fontSize"])
        if any(abs(ch["origin_y"] - baseline_y) > limit for ch in inside):
            covers_other.append(edit["opId"])
    if rotated:
        raise RewriteError("rotated_text", 400, rotated)
    if covers_other:
        raise RewriteError("box_covers_other_text", 400, covers_other)


def _original_run_chars(source_chars: list[dict], edit: dict, page) -> list[dict]:
    """
    The source page's characters that make up the run: on its baseline, from its
    baseline x, spelling `originalText`. Empty when they can't be found there.
    """
    point = _baseline_point(page, edit)
    limit = OTHER_LINE_FACTOR * float(edit["fontSize"])
    on_line = sorted(
        (ch for ch in source_chars
         if abs(ch["origin_y"] - point.y) <= limit and ch["cx"] >= point.x - VERIFY_SLACK and not ch["c"].isspace()),
        key=lambda ch: ch["cx"],
    )
    original = _squash(edit["originalText"])
    run = on_line[: len(original)]
    return run if "".join(ch["c"] for ch in run) == original else []


def _still_in_place(run: list[dict], chars: list[dict], match_font: bool) -> bool:
    """True when every character of the original run is still drawn exactly where it was (in its font)."""
    return bool(run) and all(
        any(
            ch["c"] == old["c"]
            and abs(ch["cx"] - old["cx"]) < 0.5
            and abs(ch["cy"] - old["cy"]) < 0.5
            and (not match_font or ch["font"] == old["font"])
            for ch in chars
        )
        for old in run
    )


def _verify(
    page,
    edits: list[dict],
    source_page_text: str,
    source_runs: dict[str, list[dict]],
    reused_font_ops: set[str],
) -> list[str]:
    """
    Op ids whose old text is still there, or whose new text didn't land (plan §10).

    "Still there" is checked inside the remove box, and by looking for the run's
    own characters at their original positions, so a box that missed the glyphs
    entirely is caught too (the new word drawn on top would hide that from the box check).

    The replacement is usually drawn in a different font (Liberation) than the
    original, so old characters are told apart from new ones by font. That matters
    when the new text starts with the old ("Ref: A1" -> "Ref: A1-2026"): with a
    metric-compatible font the new letters land exactly where the old ones were.
    When the original embedded font was reused, fonts can't tell them apart, and a
    replacement that contains the original is allowed (the plan's rule).
    """
    failed = []
    chars = _page_chars(page)
    page_text = page.get_text()
    for edit in edits:
        original = _squash(edit["originalText"])
        replacement = _squash(edit["text"])
        rect = _remove_rect(page, edit)
        if len(original) >= 2 and any(ch.isalnum() for ch in original) and original != replacement:
            run = source_runs.get(edit["opId"], [])
            old_fonts = {ch["font"] for ch in run}
            by_font = bool(old_fonts) and edit["opId"] not in reused_font_ops
            inside = _chars_in(chars, rect, VERIFY_SLACK)
            if by_font:
                inside = [ch for ch in inside if ch["font"] in old_fonts]
            remaining = _squash("".join(ch["c"] for ch in inside))
            if by_font:
                left_in_box = original in remaining
                left_in_place = _still_in_place(run, chars, match_font=True)
            elif original in replacement:
                # Same font, new text containing the old: indistinguishable, allowed (§10's rule).
                left_in_box = left_in_place = False
            else:
                left_in_box = original in remaining
                left_in_place = _still_in_place(run, chars, match_font=False)
            if left_in_box or left_in_place:
                failed.append(edit["opId"])
                continue
        # Compared without whitespace: a reused subset font can map its space glyph to
        # U+00A0, so "Weight: 1,800" reads back as "Weight:\xa01,800".
        new_text = _squash(edit["text"])
        if new_text and new_text not in _squash(source_page_text) and new_text not in _squash(page_text):
            failed.append(edit["opId"])
    return failed


def _layout(page, edit: dict, fontfile: str, remaining_chars: list[dict], measures: dict, warnings: list[dict]):
    """
    (text, point, size) for each line of the replacement. Without ``fit`` (older drafts),
    one line at the original baseline. With it, fitted to the slot (text_fit.fit_text),
    measured with the font the server draws with.
    """
    import fitz

    size = float(edit["fontSize"])
    fit = edit.get("fit")
    if not fit:
        return [(edit["text"], _baseline_point(page, edit), size)]
    if fontfile not in measures:
        measures[fontfile] = fitz.Font(fontfile=fontfile)
    font = measures[fontfile]

    def measure(text: str, at: float) -> float:
        return font.text_length(text, fontsize=at)

    baseline_y = float(edit["baseline"]["y"])
    layout = fit_text(edit["text"], size, baseline_y, fit, measure)
    if layout["mode"] == "wrap":
        # The editor checked the space below; check again against what is really on the page.
        blocked = any(
            _chars_in(remaining_chars, _line_rect(page, x, y, measure(text, layout["size"]), layout["size"]))
            for text, x, y in layout["lines"][1:]
        )
        if blocked:
            layout = fit_text(edit["text"], size, baseline_y, fit, measure, allow_wrap=False)
    if layout["overflow"]:
        warnings.append({"opId": edit["opId"], "code": "text_overflows"})
    return [(text, _user_point(page, x, y), layout["size"]) for text, x, y in layout["lines"]]


def rewrite_text(source_path: str, dest_path: str, edits: list[dict]) -> list[dict]:
    """
    Apply edit_text operations from source_path into dest_path.

    Returns warnings ({opId, code, font}). Raises RewriteError: 400 for a box that
    would delete other text or covers rotated text, 422 when the output still
    contains an old word. Does not modify source_path, and writes dest_path
    only after verification passes.
    """
    import fitz

    if not os.path.isabs(source_path) or not os.path.isabs(dest_path):
        raise ValueError("paths must be absolute")

    warnings: list[dict] = []
    by_page: dict[int, list[dict]] = {}
    # Copies: the colour/style read from the PDF is set on these, not on the caller's ops.
    for edit in (dict(edit) for edit in edits):
        by_page.setdefault(int(edit["page"]), []).append(edit)

    # One fitz.Font per font file, for measuring fitted text.
    measures: dict[str, object] = {}
    doc = fitz.open(source_path)
    try:
        source_text = {number: doc[number - 1].get_text() for number in by_page}
        source_runs: dict[str, list[dict]] = {}
        reused_font_ops: set[str] = set()
        for number, page_edits in by_page.items():
            source_chars = _page_chars(doc[number - 1])
            for edit in page_edits:
                run_chars = _original_run_chars(source_chars, edit, doc[number - 1])
                source_runs[edit["opId"]] = run_chars
                # The original letters decide the colour and style; the client's value is
                # only a fallback for when the run can't be found where it says.
                style = _run_style(run_chars) or _run_style(_chars_in(source_chars, _remove_rect(doc[number - 1], edit)))
                if style:
                    edit.update(color=style["color"], _bold=style["bold"], _italic=style["italic"])
        with tempfile.TemporaryDirectory(prefix="pdf-rewrite-") as tmpdir:
            for number, page_edits in by_page.items():
                page = doc[number - 1]
                _precheck(page, page_edits)
                # Resolve fonts before redacting, while the original font is still on the page.
                fonts = {edit["opId"]: resolve_font(doc, page, edit, tmpdir) for edit in page_edits}
                reused_font_ops.update(op_id for op_id, (_f, name, _w) in fonts.items() if name.startswith("RwE"))
                fonts = _subset_page_fonts(fonts, [e for e in page_edits if e["text"].strip()], tmpdir, number)

                for edit in page_edits:
                    # No fill: the replacement covers the area. A deletion leaves a white patch
                    # so what was behind the text doesn't show through (plan §7.1).
                    fill = (1, 1, 1) if not edit["text"].strip() else False
                    page.add_redact_annot(_remove_rect(page, edit), fill=fill, cross_out=False)
                # One call per page: applying one at a time rewrites the stream repeatedly.
                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE,
                )

                # Text left on the page once the old words are gone: wrapped lines mustn't land on it.
                remaining_chars = _page_chars(page)
                for edit in page_edits:
                    if not edit["text"].strip():
                        continue
                    fontfile, fontname, warning = fonts[edit["opId"]]
                    for text, point, size in _layout(page, edit, fontfile, remaining_chars, measures, warnings):
                        page.insert_text(
                            point,
                            text,
                            fontsize=size,
                            fontname=fontname,
                            fontfile=fontfile,
                            color=_parse_color(edit["color"]),
                        )
                    if warning:
                        warnings.append(warning)

            failed = []
            for number, page_edits in by_page.items():
                failed.extend(_verify(doc[number - 1], page_edits, source_text[number], source_runs, reused_font_ops))
            if failed:
                raise RewriteError("rewrite_failed", 422, failed)

            # Written only after verification passes, so a failed rewrite leaves no output.
            # garbage=4 drops objects nothing references any more, including orphaned font data.
            doc.save(dest_path, garbage=4, deflate=True)
    finally:
        doc.close()
    return warnings
