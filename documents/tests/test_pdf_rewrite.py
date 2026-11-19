"""
Rewrite engine tests (docs/plan-full-text-rewrite.md §16).

Fixtures are drawn with ReportLab at known positions, so the boxes an editor
would build from pdf.js are computed exactly here: baseline (x, y) in PDF user
space, remove = (x, y - 0.3·size, width, 1.25·size) (plan §5.1).
"""

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from documents.services.pdf_rewrite import FONT_DIR, RewriteError, rewrite_text, validate_edit_text_ops
from documents.services.pdf_text import apply_text_session

PAGE = (612, 792)
PAGES = [{"page": 1, "width": 612, "height": 792, "rotate": 0}]


def _pdf(path: Path, lines, *, image=False, rotated=None):
    """lines: [(x, y, text, font, size)] drawn left to right on one page."""
    pdf = canvas.Canvas(str(path), pagesize=PAGE)
    for x, y, text, font, size in lines:
        pdf.setFont(font, size)
        pdf.drawString(x, y, text)
    if rotated:
        x, y, text = rotated
        pdf.saveState()
        pdf.translate(x, y)
        pdf.rotate(90)
        pdf.setFont("Helvetica", 12)
        pdf.drawString(0, 0, text)
        pdf.restoreState()
    if image:
        buffer = io.BytesIO()
        Image.new("RGB", (40, 40), (200, 30, 30)).save(buffer, format="PNG")
        buffer.seek(0)
        pdf.drawImage(ImageReader(buffer), 400, 600, width=80, height=80)
    pdf.save()


def _edit(op_id, x, y, original, text, *, font="Helvetica", size=12.0, start=None, **extra):
    """An edit_text op for the word `original` drawn at baseline (x, y), or a word starting at `start`."""
    left = x if start is None else start
    op = {
        "opId": op_id,
        "op": "edit_text",
        "page": 1,
        "text": text,
        "fontSize": size,
        "color": "#000000",
        "fontName": font,
        "baseline": {"x": left, "y": y},
        "remove": {"x": left, "y": y - size * 0.3, "width": stringWidth(original, font, size), "height": size * 1.25},
        "originalText": original,
        "fallbackFont": None,
    }
    op.update(extra)
    return op


def _text(path: Path) -> str:
    with fitz.open(str(path)) as doc:
        return doc[0].get_text()


def _x_of(prefix: str, font="Helvetica", size=12.0, base=72.0) -> float:
    return base + stringWidth(prefix, font, size)


def test_replace_word_removes_old_text(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Hello World", "Helvetica", 12)])
    warnings = rewrite_text(str(src), str(out), [_edit("e1", 72, 700, "Hello", "Goodbye")])
    text = _text(out)
    assert "Goodbye" in text and "World" in text
    assert "Hello" not in text
    assert b"Hello" not in out.read_bytes()
    # Helvetica isn't embedded, so its metric twin is used without a warning.
    assert warnings == []


def test_replace_middle_of_line_keeps_neighbors(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Alpha Beta Gamma", "Helvetica", 12)])
    edit = _edit("e1", 72, 700, "Beta", "Delta", start=_x_of("Alpha "))
    rewrite_text(str(src), str(out), [edit])
    text = _text(out)
    assert "Alpha" in text and "Gamma" in text and "Delta" in text
    assert "Beta" not in text


def test_delete_run_removes_text(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Delete me", "Helvetica", 12), (72, 650, "Keep me", "Helvetica", 12)])
    rewrite_text(str(src), str(out), [_edit("e1", 72, 700, "Delete me", "")])
    text = _text(out)
    assert "Delete" not in text and "Keep me" in text


def test_accented_replacement_in_standard_font_uses_liberation(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Jose signed", "Helvetica", 12)])
    rewrite_text(str(src), str(out), [_edit("e1", 72, 700, "Jose", "José")])
    assert "José" in _text(out)
    with fitz.open(str(out)) as doc:
        names = [font[3] for font in doc[0].get_fonts(full=True)]
    assert any("Liberation" in name for name in names), names


def _embedded_font_pdf(path: Path, text: str, size=14.0, *, subset=True):
    """
    A page whose only font is embedded LiberationSerif: a true subset (just the
    glyphs of `text`, like a word-processor export) or the full font.
    """
    doc = fitz.open()
    page = doc.new_page(width=PAGE[0], height=PAGE[1])
    page.insert_text((72, PAGE[1] - 700), text, fontsize=size, fontname="SubSerif",
                     fontfile=f"{FONT_DIR}/LiberationSerif-Regular.ttf")
    if subset:
        doc.subset_fonts()
    doc.save(str(path), garbage=4, deflate=True)
    doc.close()
    with fitz.open(str(path)) as reopened:
        return next(f[3] for f in reopened[0].get_fonts(full=True))


def _serif_width(text: str, size=14.0) -> float:
    return fitz.Font(fontfile=f"{FONT_DIR}/LiberationSerif-Regular.ttf").text_length(text, fontsize=size)


def test_embedded_font_reused_when_it_covers_the_text(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    font_name = _embedded_font_pdf(src, "abc", subset=False)
    edit = _edit("e1", 72, 700, "abc", "Zyx", size=14, fontName=font_name)
    edit["remove"]["width"] = _serif_width("abc")
    assert rewrite_text(str(src), str(out), [edit]) == []
    assert "Zyx" in _text(out) and "abc" not in _text(out)


def test_subset_font_missing_glyph_falls_back_with_warning(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    font_name = _embedded_font_pdf(src, "abc")
    edit = _edit("e1", 72, 700, "abc", "Zyx", size=14, fontName=font_name)
    edit["remove"]["width"] = _serif_width("abc")
    warnings = rewrite_text(str(src), str(out), [edit])
    assert "Zyx" in _text(out) and "abc" not in _text(out)
    assert warnings == [{"opId": "e1", "code": "font_replaced", "font": "LiberationSerif"}]


def test_character_no_font_can_draw_is_refused(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Hello", "Helvetica", 12)])
    with pytest.raises(RewriteError) as caught:
        rewrite_text(str(src), str(out), [_edit("e1", 72, 700, "Hello", "漢字")])
    assert caught.value.reason == "unsupported_character"
    assert not out.exists()


def test_client_requested_fallback(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Courier text", "Courier", 12)])
    edit = _edit("e1", 72, 700, "Courier", "Mono", font="Courier", fallbackFont="LiberationMono")
    warnings = rewrite_text(str(src), str(out), [edit])
    text = _text(out)
    assert "Mono" in text and "text" in text and "Courier" not in text
    assert warnings == [{"opId": "e1", "code": "font_replaced", "font": "LiberationMono"}]


def test_two_edits_on_one_page(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "First line", "Helvetica", 12), (72, 650, "Second line", "Helvetica", 12)])
    rewrite_text(
        str(src),
        str(out),
        [_edit("e1", 72, 700, "First", "One"), _edit("e2", 72, 650, "Second", "Two")],
    )
    text = _text(out)
    assert "One" in text and "Two" in text
    assert "First" not in text and "Second" not in text


def test_rewrite_then_add_text(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Hello World", "Helvetica", 12)])
    add = {
        "opId": "a1", "op": "add_text", "page": 1, "x": 72, "y": 680, "width": 200, "height": 20,
        "text": "Added box", "font": "Helvetica", "fontSize": 12, "color": "#000000",
        "bold": False, "italic": False, "align": "left",
    }
    # The added box overlaps the rewritten word: rewrites run first, so it survives.
    apply_text_session(str(src), str(out), [add, _edit("e1", 72, 700, "Hello", "Goodbye")])
    text = _text(out)
    assert "Goodbye" in text and "Added box" in text
    assert "Hello" not in text


def test_rewrite_does_not_remove_image(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Hello World", "Helvetica", 12)], image=True)
    rewrite_text(str(src), str(out), [_edit("e1", 72, 700, "Hello", "Goodbye")])
    with fitz.open(str(out)) as doc:
        assert doc[0].get_images()


def test_box_covering_next_line_rejected(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Top line", "Helvetica", 12), (72, 686, "Next line", "Helvetica", 12)])
    before = src.read_bytes()
    edit = _edit("e1", 72, 700, "Top line", "Changed")
    edit["remove"] = {"x": 72, "y": 680, "width": 80, "height": 30}  # reaches into the line below
    with pytest.raises(RewriteError) as caught:
        rewrite_text(str(src), str(out), [edit])
    assert caught.value.reason == "box_covers_other_text"
    assert caught.value.status_code == 400
    assert src.read_bytes() == before
    assert not out.exists()


def test_rotated_run_rejected(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [], rotated=(300, 300, "Sideways"))
    edit = _edit("e1", 300, 300, "Sideways", "Up")
    edit["remove"] = {"x": 288, "y": 295, "width": 16, "height": 50}
    with pytest.raises(RewriteError) as caught:
        rewrite_text(str(src), str(out), [edit])
    assert caught.value.reason == "rotated_text"


def test_box_that_misses_the_word_fails_verification(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Hello World", "Helvetica", 12)])
    edit = _edit("e1", 72, 700, "Hello", "Goodbye")
    edit["remove"]["x"] = 300  # empty space: nothing is deleted, the old word stays
    with pytest.raises(RewriteError) as caught:
        rewrite_text(str(src), str(out), [edit])
    assert caught.value.reason == "rewrite_failed"
    assert caught.value.op_ids == ["e1"]
    assert not out.exists()


def test_add_text_only_session_does_not_use_rewrite(tmp_path, monkeypatch):
    import documents.services.pdf_rewrite as rewrite_module

    def boom(*_args, **_kwargs):
        raise AssertionError("rewrite_text must not run for add_text-only sessions")

    monkeypatch.setattr(rewrite_module, "rewrite_text", boom)
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Original", "Helvetica", 12)])
    add = {
        "opId": "a1", "op": "add_text", "page": 1, "x": 72, "y": 40, "width": 200, "height": 20,
        "text": "New words", "font": "Helvetica", "fontSize": 12, "color": "#000000",
        "bold": False, "italic": False, "align": "left",
    }
    assert apply_text_session(str(src), str(out), [add]) == []
    text = _text(out)
    assert "Original" in text and "New words" in text


def test_plan1_text_can_be_rewritten_later(tmp_path):
    """Plan §14: text baked by add-text is ordinary page text and can be edited."""
    src, mid, out = tmp_path / "in.pdf", tmp_path / "mid.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Body", "Helvetica", 12)])
    add = {
        "opId": "a1", "op": "add_text", "page": 1, "x": 72, "y": 100, "width": 200, "height": 20,
        "text": "Invoice", "font": "Helvetica", "fontSize": 12, "color": "#000000",
        "bold": False, "italic": False, "align": "left",
    }
    apply_text_session(str(src), str(mid), [add])
    # add_text draws its baseline at 0.8·size below the top of its box (top-left frame).
    baseline_y = PAGE[1] - (100 + 12 * 0.8)
    apply_text_session(str(mid), str(out), [_edit("e1", 72, baseline_y, "Invoice", "Receipt")])
    text = _text(out)
    assert "Receipt" in text and "Invoice" not in text and "Body" in text


class TestValidation:
    def test_valid_op(self):
        assert validate_edit_text_ops([_edit("e1", 72, 700, "Hello", "Hi")], PAGES) == []

    def test_box_taller_than_four_times_font_size(self):
        op = _edit("e1", 72, 700, "Hello", "Hi")
        op["remove"]["height"] = 60
        assert [e["reason"] for e in validate_edit_text_ops([op], PAGES)] == ["invalid_box"]

    def test_off_page_and_bad_fields(self):
        off = _edit("e1", 72, 700, "Hello", "Hi")
        off["remove"]["x"] = 700
        bad = _edit("e2", 72, 600, "Hello", "Hi", color="red", fallbackFont="Comic")
        reasons = {e["reason"] for e in validate_edit_text_ops([off, bad], PAGES)}
        assert {"off_page", "invalid_color", "invalid_font"} <= reasons

    def test_overlapping_boxes(self):
        a = _edit("e1", 72, 700, "Hello", "Hi")
        b = _edit("e2", 80, 700, "Hello", "Yo")
        assert [e["reason"] for e in validate_edit_text_ops([a, b], PAGES)] == ["boxes_overlap"]


def test_embedded_subset_with_standard_name_still_warns(tmp_path):
    """An embedded "ABCDEF+Arial" subset lacking letters is a real replacement, not a silent twin."""
    from documents.services.pdf_rewrite import resolve_font

    class FakePage:
        def get_fonts(self, full=True):
            return [(9, "ttf", "TrueType", "ABCDEF+Arial", "F1", "", 0)]

    class FakeDoc:
        def extract_font(self, xref):
            # A buffer PyMuPDF can't open as a font: the subset can't be reused.
            return ("Arial", "ttf", "TrueType", b"not a font")

    edit = {"opId": "e1", "text": "Zebra", "fontName": "ABCDEF+Arial", "fallbackFont": None}
    fontfile, _name, warning = resolve_font(FakeDoc(), FakePage(), edit, str(tmp_path))
    assert fontfile.endswith("LiberationSans-Regular.ttf")
    assert warning == {"opId": "e1", "code": "font_replaced", "font": "LiberationSans"}


def test_standard_font_never_embedded_uses_twin_quietly(tmp_path):
    from documents.services.pdf_rewrite import resolve_font

    class FakePage:
        def get_fonts(self, full=True):
            return [(2, "n/a", "Type1", "Times-Bold", "F1", "WinAnsiEncoding", 0)]

    edit = {"opId": "e1", "text": "Zebra", "fontName": "Times-Bold", "fallbackFont": None}
    fontfile, _name, warning = resolve_font(object(), FakePage(), edit, str(tmp_path))
    assert fontfile.endswith("LiberationSerif-Bold.ttf")
    assert warning is None


def test_replacement_that_starts_with_the_original(tmp_path):
    """Metric-compatible fonts put the new letters exactly where the old ones were; fonts tell them apart."""
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 640, "Ref: A1", "Helvetica", 14)])
    edit = _edit("e1", 72, 640, "Ref: A1", "Ref: A1-2026-LAGOS", size=14)
    rewrite_text(str(src), str(out), [edit])
    with fitz.open(str(out)) as doc:
        spans = [s for b in doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    assert "Ref: A1-2026-LAGOS" in _text(out)
    assert all("Helvetica" not in s["font"] for s in spans), [s["font"] for s in spans]


def test_replacement_that_starts_with_the_original_but_box_missed(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 640, "Ref: A1", "Helvetica", 14)])
    edit = _edit("e1", 72, 640, "Ref: A1", "Ref: A1-2026", size=14)
    edit["remove"]["x"] = 400  # deletes nothing; the old Helvetica letters stay under the new ones
    with pytest.raises(RewriteError) as caught:
        rewrite_text(str(src), str(out), [edit])
    assert caught.value.reason == "rewrite_failed"


def _coloured_pdf(path: Path):
    pdf = canvas.Canvas(str(path), pagesize=PAGE)
    pdf.setFont("Helvetica", 14)
    pdf.setFillColorRGB(0.5, 0.5, 0.5)  # grey, like "Weight: 1,759.5kg" on the Hivolt invoice
    pdf.drawString(72, 700, "Weight: 1,759.5kg")
    pdf.setFillColorRGB(0.65, 0.11, 0.0)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 650, "HIVOLT ENTERPRISE")
    pdf.save()


def _span_styles(path: Path):
    with fitz.open(str(path)) as doc:
        return {
            s["text"]: (f"#{s['color']:06x}", bool(s["flags"] & 16))
            for b in doc[0].get_text("dict")["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            if s["text"].strip()
        }


def test_replacement_keeps_the_original_colour_even_if_client_sends_black(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _coloured_pdf(src)
    edit = _edit("e1", 72, 700, "Weight: 1,759.5kg", "Weight: 1,800.0kg", size=14, color="#000000")
    rewrite_text(str(src), str(out), [edit])
    color, _bold = _span_styles(out)["Weight: 1,800.0kg"]
    assert color == "#808080"
    assert edit["color"] == "#000000"  # the caller's op is not modified


def test_bold_coloured_heading_stays_bold_and_coloured(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _coloured_pdf(src)
    edit = _edit("e1", 72, 650, "HIVOLT ENTERPRISE", "MALIK ENTERPRISE", font="Helvetica-Bold", size=14)
    rewrite_text(str(src), str(out), [edit])
    color, bold = _span_styles(out)["MALIK ENTERPRISE"]
    assert color == "#a61c00"
    assert bold
    with fitz.open(str(out)) as doc:
        assert any("Liberation Sans Bold" in f[3] or "LiberationSans-Bold" in f[3] for f in doc[0].get_fonts(full=True))


def test_page_text_styles_reports_colour_style_and_user_space_box(tmp_path):
    from documents.services.pdf_rewrite import page_text_styles

    src = tmp_path / "in.pdf"
    _coloured_pdf(src)
    [page] = page_text_styles(str(src))
    by_colour = {entry[4]: entry for entry in page}
    grey = by_colour["#808080"]
    red = by_colour["#a61c00"]
    assert grey[5] is False and red[5] is True
    # Bottom-left origin: the grey line (baseline 700) is above the red one (baseline 650).
    assert grey[1] > red[1]
    assert grey[0] == pytest.approx(72, abs=1) and grey[1] < 700 < grey[3]


def test_reused_embedded_font_extension_of_the_original_is_allowed(tmp_path):
    """Same font, new text starting with the old ("Zenith Bank" -> "Zenith Bank Plc"): allowed."""
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    font_name = _embedded_font_pdf(src, "Zenith Bank Plc and more", subset=False)
    edit = _edit("e1", 72, 700, "Zenith Bank", "Zenith Bank Ltd", size=14, fontName=font_name)
    edit["remove"]["width"] = _serif_width("Zenith Bank")
    # Only part of the line is the run in this fixture; delete just "Zenith Bank".
    assert rewrite_text(str(src), str(out), [edit]) == []
    assert "Zenith Bank Ltd" in _text(out)


def test_embedded_font_found_by_its_real_name(tmp_path):
    """The editor sends the name inside the font program ("Liberation Serif"), not the PDF's ("...+LiberationSerif")."""
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _embedded_font_pdf(src, "abc", subset=False)
    edit = _edit("e1", 72, 700, "abc", "Zyx", size=14, fontName="Liberation Serif")
    edit["remove"]["width"] = _serif_width("abc")
    assert rewrite_text(str(src), str(out), [edit]) == []


def test_page_text_styles_names_a_loadable_embedded_font(tmp_path):
    from documents.services.pdf_rewrite import extract_preview_font, page_text_styles

    src = tmp_path / "in.pdf"
    _embedded_font_pdf(src, "Invoice 42", subset=False)
    [page] = page_text_styles(str(src))
    font_id = page[0][8]
    assert font_id is not None
    data, content_type = extract_preview_font(str(src), int(font_id))
    assert content_type == "font/ttf"
    assert set("Invoice42") <= {chr(c) for c in fitz.Font(fontbuffer=data).valid_codepoints()}


def test_standard_fonts_and_unknown_xrefs_have_no_preview_font(tmp_path):
    from documents.services.pdf_rewrite import extract_preview_font, page_text_styles

    src = tmp_path / "in.pdf"
    _coloured_pdf(src)  # Helvetica: nothing embedded
    assert all(span[8] is None for span in page_text_styles(str(src))[0])
    assert extract_preview_font(str(src), 1) is None
    assert extract_preview_font(str(src), 99999) is None


def test_subset_without_a_unicode_map_has_no_preview_font(tmp_path):
    """PyMuPDF's own subsets drop the cmap: a browser couldn't map typed letters to glyphs."""
    from documents.services.pdf_rewrite import page_text_styles

    src = tmp_path / "in.pdf"
    _embedded_font_pdf(src, "Invoice 42", subset=True)
    assert page_text_styles(str(src))[0][0][8] is None


# --- Borders and alignment ------------------------------------------------------------


def _fit(left, right, bottom, align="left", anchor=None):
    return {"left": left, "right": right, "bottom": bottom, "align": align,
            "anchor": left if anchor is None else anchor}


def _spans(path: Path):
    with fitz.open(str(path)) as doc:
        page = doc[0]
        to_user = ~page.transformation_matrix
        out = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        box = fitz.Rect(span["bbox"]) * to_user
                        box.normalize()
                        out.append((span["text"].strip(), round(span["size"], 2), box, span["origin"]))
        return out


def test_fitted_edit_shrinks_to_stay_inside_its_cell(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Amount", "Helvetica", 12), (72, 686, "Next line", "Helvetica", 12)])
    edit = _edit("e1", 72, 700, "Amount", "Amount payable", fit=_fit(72, 150, 699))
    rewrite_text(str(src), str(out), [edit])
    [(text, size, box, _origin)] = [s for s in _spans(out) if "payable" in s[0]]
    assert text == "Amount payable"
    assert 9 <= size < 12
    assert box.x1 <= 151


def test_fitted_edit_wraps_into_empty_space_below(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Note", "Helvetica", 12), (72, 600, "Far below", "Helvetica", 12)])
    long_text = "This note is now a good deal longer than before"
    edit = _edit("e1", 72, 700, "Note", long_text, fit=_fit(72, 200, 620))
    assert rewrite_text(str(src), str(out), [edit]) == []
    lines = [s for s in _spans(out) if s[0] != "Far below"]
    assert len(lines) >= 2 and all(size == 12 for _t, size, _b, _o in lines)
    assert all(box.x1 <= 201 for _t, _s, box, _o in lines)
    assert " ".join(t for t, *_ in lines) == long_text
    assert "Far below" in _text(out)


def test_wrap_is_refused_when_text_is_in_the_way(tmp_path):
    """The editor said there was room; the page says otherwise: one line, shrunk or overflowing."""
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Note", "Helvetica", 12), (72, 686, "Blocking line", "Helvetica", 12)])
    long_text = "This note is now a good deal longer than before"
    edit = _edit("e1", 72, 700, "Note", long_text, fit=_fit(72, 200, 620))
    warnings = rewrite_text(str(src), str(out), [edit])
    replaced = [s for s in _spans(out) if s[0] == long_text]
    assert len(replaced) == 1
    assert warnings == [{"opId": "e1", "code": "text_overflows"}]


def test_right_aligned_edit_keeps_its_right_edge(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    right = 400.0
    width = stringWidth("1,000.00", "Helvetica", 12)
    _pdf(src, [(right - width, 700, "1,000.00", "Helvetica", 12)])
    edit = _edit("e1", right - width, 700, "1,000.00", "12,345.67",
                 fit=_fit(300, 410, 699, align="right", anchor=right))
    rewrite_text(str(src), str(out), [edit])
    [(_t, _s, box, _o)] = _spans(out)
    assert box.x1 == pytest.approx(right, abs=0.6)


def test_invalid_fit_is_refused():
    edit = _edit("e1", 72, 700, "Amount", "x", fit=_fit(150, 72, 699))
    assert [e["reason"] for e in validate_edit_text_ops([edit], PAGES)] == ["invalid_fit"]


def test_page_rules_finds_lines_thin_boxes_and_box_edges(tmp_path):
    from documents.services.pdf_rewrite import page_rules

    src = tmp_path / "in.pdf"
    pdf = canvas.Canvas(str(src), pagesize=PAGE)
    pdf.rect(0, 0, *PAGE, stroke=0, fill=1)  # page background: ignored
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(10, 10, 50, 50, stroke=0, fill=1)  # white patch: ignored
    pdf.line(100, 500, 100, 700)  # vertical rule
    pdf.setFillColorRGB(0, 0, 0)
    pdf.rect(200, 400, 300, 0.5, stroke=0, fill=1)  # table border drawn as a thin box
    pdf.rect(300, 100, 100, 50, stroke=1, fill=0)  # a box: four edges
    pdf.save()
    [rules] = page_rules(str(src))
    assert [0, 100.0, 500.0, 700.0] in rules
    assert any(r[0] == 1 and r[1] == pytest.approx(400.2, abs=0.2) and r[2] == 200 and r[3] == 500 for r in rules)
    assert {(r[0], r[1]) for r in rules} >= {(0, 300.0), (0, 400.0), (1, 100.0), (1, 150.0)}
    assert not any(r[1] in (10.0, 60.0) for r in rules)
    assert not any(r[1] in (0.0, 612.0, 792.0) for r in rules)


def test_added_fonts_are_subset_and_keep_their_character_map(tmp_path):
    """A Liberation fallback is a few KB, not 400 KB, and a later edit can still reuse it."""
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Amount", "Helvetica", 12)])
    edit = _edit("e1", 72, 700, "Amount", "Total due", fallbackFont="LiberationSans")
    rewrite_text(str(src), str(out), [edit])
    with fitz.open(str(out)) as doc:
        [(xref, *_rest)] = [f for f in doc[0].get_fonts(full=True) if "Liberation" in f[3]]
        buffer = doc.extract_font(xref)[3]
    assert len(buffer) < 40_000
    assert set("Totaldue") <= {chr(c) for c in fitz.Font(fontbuffer=buffer).valid_codepoints()}
    assert "Total due" in _text(out)


def test_two_edits_on_a_page_share_one_subset(tmp_path):
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    _pdf(src, [(72, 700, "Alpha", "Helvetica", 12), (72, 650, "Beta", "Helvetica", 12)])
    edits = [
        _edit("e1", 72, 700, "Alpha", "Xylophone", fallbackFont="LiberationSans"),
        _edit("e2", 72, 650, "Beta", "Quartz", fallbackFont="LiberationSans"),
    ]
    rewrite_text(str(src), str(out), edits)
    text = _text(out)
    assert "Xylophone" in text and "Quartz" in text


def test_a_later_edit_reuses_the_full_font_not_an_earlier_small_subset(tmp_path):
    src, mid, out = tmp_path / "in.pdf", tmp_path / "mid.pdf", tmp_path / "out.pdf"
    font_name = _embedded_font_pdf(src, "abc and more words", subset=False)
    first = _edit("e1", 72, 700, "abc", "ab", size=14, fontName=font_name)
    first["remove"]["width"] = _serif_width("abc")
    rewrite_text(str(src), str(mid), [first])
    # The page now has the full font and a two-letter subset of it, both named the same.
    start = 72 + _serif_width("ab ")
    second = _edit("e2", 72, 700, "and", "zebra", size=14, fontName=font_name, start=start)
    second["remove"]["width"] = _serif_width("and")
    assert rewrite_text(str(mid), str(out), [second]) == []
