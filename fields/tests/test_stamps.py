"""
Server-filled field rules: date from the signing instant in the signer's zone,
initials from the account name, text fitted to the field box, text retired.
"""

import io
import os
from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from rest_framework import serializers

from fields.stamps import (
    DATE_FORMATS,
    DEFAULT_INITIALS_FONT,
    INITIALS_FONTS,
    build_stamp_options,
    fit_font_size,
    format_signing_date,
    initials_reportlab_font,
    initials_text,
    normalize_timezone,
)
from fields.validation import clean_field_values, validate_field_item
from signatures.services.signing import build_field_stamps
from signatures.utils.pdf_signing import embed_fields_single_pass

# 23:30 UTC on 18 Nov is already 19 Nov in Lagos (UTC+1).
SIGNED_AT = datetime(2026, 11, 18, 23, 30, tzinfo=dt_timezone.utc)


class TestTimezone:
    def test_valid_zone_is_kept(self):
        assert normalize_timezone("Europe/London") == "Europe/London"

    @pytest.mark.parametrize("value", [None, "", "  ", "Mars/Olympus", 42, "x" * 80])
    def test_missing_or_invalid_falls_back_to_lagos(self, value):
        assert normalize_timezone(value) == "Africa/Lagos"


class TestSigningDate:
    def test_uses_signer_zone_not_utc(self):
        assert format_signing_date(SIGNED_AT, "Africa/Lagos", "DD/MM/YYYY") == "19/11/2026"
        assert format_signing_date(SIGNED_AT, "America/New_York", "DD/MM/YYYY") == "18/11/2026"

    def test_every_format(self):
        expected = {
            "DD/MM/YYYY": "19/11/2026",
            "MM/DD/YYYY": "11/19/2026",
            "YYYY-MM-DD": "2026-11-19",
            "YYYY/MM/DD": "2026/11/19",
            "DD-MMM-YYYY": "19-Nov-2026",
            "MMM D, YYYY": "Nov 19, 2026",
            "D MMMM YYYY": "19 November 2026",
        }
        assert set(expected) == set(DATE_FORMATS)
        for fmt, text in expected.items():
            assert format_signing_date(SIGNED_AT, "Africa/Lagos", fmt) == text

    def test_unknown_format_uses_default(self):
        assert format_signing_date(SIGNED_AT, None, "nonsense") == "2026-11-19"


class TestInitials:
    @pytest.mark.parametrize(
        "style,expected",
        [
            ("initials", "AA"),
            ("first_name", "Abdulmalik"),
            ("last_name", "Aremu"),
            ("full_name", "Abdulmalik Aremu"),
            ("bogus", "AA"),
            (None, "AA"),
        ],
    )
    def test_styles(self, style, expected):
        assert initials_text("  Abdulmalik   Aremu ", style) == expected

    def test_middle_names_and_empty(self):
        assert initials_text("abdulmalik olawale aremu", "initials") == "AOA"
        assert initials_text("", "initials") == ""
        assert initials_text(None, "full_name") == ""

    @pytest.mark.parametrize("font_id", list(INITIALS_FONTS))
    def test_every_font_registers_and_measures(self, font_id):
        name = initials_reportlab_font(font_id)
        assert stringWidth("AA", name, 20) > 0

    def test_unknown_font_uses_default(self):
        assert initials_reportlab_font("comic-sans") == initials_reportlab_font(DEFAULT_INITIALS_FONT)


class TestStampOptions:
    def test_defaults(self):
        assert build_stamp_options({}) == {
            "timezone": "Africa/Lagos",
            "initials_style": "initials",
            "initials_font": "great-vibes",
        }

    def test_keeps_valid_choices(self):
        options = build_stamp_options(
            {"timezone": "Europe/Paris", "initials_style": "full_name", "initials_font": "allura"}
        )
        assert options == {"timezone": "Europe/Paris", "initials_style": "full_name", "initials_font": "allura"}


class TestFit:
    def test_long_text_shrinks_to_fit_width(self):
        size = fit_font_size("A very long designation for a small box", "Helvetica", 80, 30, 12)
        assert stringWidth("A very long designation for a small box", "Helvetica", size) <= 80 - 8 + 0.01

    def test_short_text_capped_by_max_and_height(self):
        assert fit_font_size("AA", "Helvetica", 200, 30, 12) == 12
        assert fit_font_size("AA", "Helvetica", 200, 10, None) == pytest.approx(7)


def _field(**kw):
    base = dict(page=1, x=50.0, y=100.0, width=160.0, height=30.0, font_family=None,
                font_size=None, date_format=None, prefill_value=None, value=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestBuildFieldStamps:
    signer = SimpleNamespace(full_name="Abdulmalik Aremu")

    def test_date_from_signing_instant_ignores_client_value(self):
        field = _field(type="date", date_format="DD/MM/YYYY", value="01/01/1999")
        [stamp] = build_field_stamps([field], self.signer, {"signed_at": SIGNED_AT, "timezone": "Africa/Lagos"})
        assert stamp["text"] == "19/11/2026"
        assert (stamp["width"], stamp["height"], stamp["align"]) == (160.0, 30.0, "left")

    def test_legacy_date_prefill_is_honoured(self):
        field = _field(type="date", prefill_value="2025-01-01")
        [stamp] = build_field_stamps([field], self.signer, {"signed_at": SIGNED_AT})
        assert stamp["text"] == "2025-01-01"

    def test_initials_from_name_style_and_font(self):
        field = _field(type="initials", value="ZZ")
        [stamp] = build_field_stamps(
            [field], self.signer,
            {"signed_at": SIGNED_AT, "initials_style": "last_name", "initials_font": "allura"},
        )
        assert stamp["text"] == "Aremu"
        assert stamp["font_family"] == "Initials-allura"
        assert stamp["align"] == "center"
        assert stamp["max_font_size"] is None

    def test_designation_uses_value(self):
        [stamp] = build_field_stamps([_field(type="designation", value="Director")], self.signer, None)
        assert stamp["text"] == "Director"

    def test_empty_values_are_skipped(self):
        assert build_field_stamps([_field(type="designation")], self.signer, None) == []


def test_embed_draws_fitted_initials(tmp_path):
    source = tmp_path / "in.pdf"
    buffer = io.BytesIO()
    blank = canvas.Canvas(buffer, pagesize=(612, 792))
    blank.showPage()
    blank.save()
    source.write_bytes(buffer.getvalue())
    output = tmp_path / "out.pdf"

    stamps = build_field_stamps(
        [_field(type="initials"), _field(type="date", y=200.0, date_format="D MMMM YYYY")],
        SimpleNamespace(full_name="Abdulmalik Aremu"),
        {"signed_at": SIGNED_AT, "initials_font": "great-vibes"},
    )
    embed_fields_single_pass(pdf_path=str(source), output_path=str(output), text_stamps=stamps)

    assert os.path.getsize(output) > 0
    page = PdfReader(str(output)).pages[0]
    fonts = page["/Resources"]["/Font"]
    base_fonts = {str(fonts[key].get_object()["/BaseFont"]) for key in fonts}
    assert any("GreatVibes" in name for name in base_fonts)
    assert "19 November 2026" in page.extract_text()


class TestValidation:
    def _item(self, **kw):
        item = {"document_id": "d1", "page": 1, "x": 0, "y": 0, "width": 10, "height": 10,
                "type": "date", "required": False}
        item.update(kw)
        return item

    def _validate(self, item, **kw):
        validate_field_item(item, 0, document_ids={"d1"}, required_keys=("document_id", "type"), **kw)

    def test_text_is_retired(self):
        with pytest.raises(serializers.ValidationError, match="Add text"):
            self._validate(self._item(type="text"))

    def test_unknown_date_format_rejected(self):
        with pytest.raises(serializers.ValidationError, match="date_format"):
            self._validate(self._item(date_format="DD.MM.YY"))

    def test_required_date_needs_no_value(self):
        self._validate(self._item(required=True), require_value_when_required=True)

    def test_required_designation_needs_value(self):
        with pytest.raises(serializers.ValidationError):
            self._validate(self._item(type="designation", required=True), require_value_when_required=True)

    def test_clean_drops_client_values_for_server_filled_types(self):
        assert clean_field_values({"type": "initials", "value": "AA", "prefill_value": "AA"})["value"] is None
        assert clean_field_values({"type": "designation", "value": "CEO"})["value"] == "CEO"
