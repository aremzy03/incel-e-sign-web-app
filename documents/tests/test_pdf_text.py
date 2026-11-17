import io
import os
import re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from documents.services.pdf_text import PLACEHOLDER_TEXT, apply_add_text


def _source_with_hello(path, width=612, height=792):
    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=(width, height))
    pdf.drawString(72, 72, "Hello")
    pdf.showPage()
    pdf.drawString(72, 72, "Second")
    pdf.save()
    path.write_bytes(packet.getvalue()) if hasattr(path, "write_bytes") else None


def _write_hello(path: str, width=612, height=792) -> None:
    pdf = canvas.Canvas(path, pagesize=(width, height))
    pdf.drawString(72, 100, "Hello")
    pdf.showPage()
    pdf.drawString(72, 100, "Second")
    pdf.save()


def _text_positions(path: str):
    reader = PdfReader(path)
    found = []
    for page in reader.pages:
        content = page.get_contents()
        if content is None:
            data = b""
        else:
            data = content.get_data()
        for match in re.finditer(rb"1 0 0 1 ([0-9.]+) ([0-9.]+) Tm", data):
            found.append((float(match.group(1)), float(match.group(2))))
    return found


def _extracted(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _op(**overrides):
    base = {
        "opId": "box-1",
        "op": "add_text",
        "page": 1,
        "x": 72,
        "y": 0,
        "width": 180,
        "height": 20,
        "text": "Invoice",
        "font": "Helvetica",
        "fontSize": 10,
        "color": "#000000",
        "bold": False,
        "italic": False,
        "align": "left",
    }
    base.update(overrides)
    return base


def test_add_text_keeps_original_text(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    before = source.read_bytes()
    apply_add_text(str(source), str(dest), [_op()])
    text = _extracted(str(dest))
    assert "Hello" in text
    assert "Invoice" in text
    assert source.read_bytes() == before


def test_add_text_top_left_origin(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    font_size = 10
    apply_add_text(str(source), str(dest), [_op(fontSize=font_size, y=0, text="Top")])
    positions = _text_positions(str(dest))
    top_positions = [pos for pos in positions if abs(pos[0] - 72) < 1]
    assert top_positions
    page_height = 792
    expected = page_height - font_size
    assert any(abs(pos[1] - expected) <= 2 for pos in top_positions)


def test_add_text_two_boxes_one_pass(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    before = source.read_bytes()
    apply_add_text(
        str(source),
        str(dest),
        [
            _op(opId="a", text="Alpha", y=40),
            _op(opId="b", text="Beta", y=80),
            _op(opId="c", text="Gamma", page=2, y=40),
        ],
    )
    reader = PdfReader(str(dest))
    assert len(reader.pages) == 2
    text = _extracted(str(dest))
    assert "Alpha" in text and "Beta" in text and "Gamma" in text
    assert source.read_bytes() == before


def test_add_text_clips_overflow_line(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    apply_add_text(
        str(source),
        str(dest),
        [_op(text="Visible\nOVERFLOW", fontSize=12, height=16, y=40, width=200)],
    )
    text = _extracted(str(dest))
    assert "Visible" in text
    assert "OVERFLOW" not in text


def test_add_text_alignment_center(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    text = "Center"
    font_size = 12
    width = 180
    x = 72
    apply_add_text(
        str(source),
        str(dest),
        [_op(text=text, align="center", fontSize=font_size, width=width, x=x, y=40, height=30)],
    )
    measured = stringWidth(text, "Helvetica", font_size)
    expected_x = x + (width - measured) / 2
    positions = _text_positions(str(dest))
    assert any(abs(pos[0] - expected_x) <= 1 for pos in positions)


def test_add_text_preserves_acroform(tmp_path):
    source = tmp_path / "form.pdf"
    dest = tmp_path / "form-out.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(612, 792))
    pdf.drawString(72, 700, "Hello")
    pdf.acroForm.textfield(name="signer", x=72, y=640, width=200, height=20)
    pdf.save()
    apply_add_text(str(source), str(dest), [_op(text="Invoice", y=100)])
    fields = PdfReader(str(dest)).get_fields() or {}
    assert "signer" in fields
    assert "Invoice" in _extracted(str(dest))
    assert "Hello" in _extracted(str(dest))


def test_placeholder_and_blank_skipped(tmp_path):
    source = tmp_path / "source.pdf"
    dest = tmp_path / "dest.pdf"
    _write_hello(str(source))
    apply_add_text(
        str(source),
        str(dest),
        [
            _op(opId="blank", text=""),
            _op(opId="space", text="   "),
            _op(opId="placeholder", text=PLACEHOLDER_TEXT),
        ],
    )
    text = _extracted(str(dest))
    assert "Hello" in text
    assert PLACEHOLDER_TEXT not in text
    assert "Invoice" not in text
