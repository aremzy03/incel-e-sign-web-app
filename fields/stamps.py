"""
What gets drawn for a non-signature field, and how.

The server is the authority for these values:

* Date fields show the moment the signer pressed "sign" (the signing job's
  creation time, from the server clock) in the signer's browser time zone.
  The browser only tells us *which* zone; it never supplies the date itself.
* Initials fields are derived from the signer's account name in the style and
  handwriting font the signer chose.

The frontend mirrors these lists for its live preview
(`src/lib/fields/stamps.ts`); `fields/tests/test_stamps.py` pins them.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont

# --- Time zone -------------------------------------------------------------

# Most signers are in Lagos; used whenever the browser sends nothing usable.
DEFAULT_SIGNER_TIMEZONE = "Africa/Lagos"


def normalize_timezone(name: object) -> str:
    """Return a valid IANA zone name, falling back to Africa/Lagos."""
    if not isinstance(name, str) or not name.strip() or len(name) > 64:
        return DEFAULT_SIGNER_TIMEZONE
    candidate = name.strip()
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_SIGNER_TIMEZONE
    return candidate


# --- Date formats ----------------------------------------------------------

_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_LONG = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Matches what fields created before this module were drawn with.
DEFAULT_DATE_FORMAT = "YYYY-MM-DD"

# Locale-independent on purpose: strftime month names follow the server locale.
_DATE_FORMATTERS = {
    "DD/MM/YYYY": lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}",
    "MM/DD/YYYY": lambda d: f"{d.month:02d}/{d.day:02d}/{d.year}",
    "YYYY-MM-DD": lambda d: f"{d.year}-{d.month:02d}-{d.day:02d}",
    "YYYY/MM/DD": lambda d: f"{d.year}/{d.month:02d}/{d.day:02d}",
    "DD-MMM-YYYY": lambda d: f"{d.day:02d}-{_MONTHS_SHORT[d.month - 1]}-{d.year}",
    "MMM D, YYYY": lambda d: f"{_MONTHS_SHORT[d.month - 1]} {d.day}, {d.year}",
    "D MMMM YYYY": lambda d: f"{d.day} {_MONTHS_LONG[d.month - 1]} {d.year}",
}
DATE_FORMATS = tuple(_DATE_FORMATTERS)


def format_signing_date(signed_at: datetime, timezone_name: str | None, date_format: str | None) -> str:
    """Format the server-side signing instant in the signer's zone."""
    local = signed_at.astimezone(ZoneInfo(normalize_timezone(timezone_name)))
    formatter = _DATE_FORMATTERS.get(date_format or "", _DATE_FORMATTERS[DEFAULT_DATE_FORMAT])
    return formatter(local)


# --- Initials --------------------------------------------------------------

INITIALS_STYLES = ("initials", "first_name", "last_name", "full_name")
DEFAULT_INITIALS_STYLE = "initials"


def initials_text(full_name: str | None, style: str | None) -> str:
    """
    Text for an initials field.

    "Abdulmalik Aremu" -> initials "AA", first_name "Abdulmalik",
    last_name "Aremu", full_name "Abdulmalik Aremu".
    """
    parts = [p for p in (full_name or "").split() if p]
    if not parts:
        return ""
    style = style if style in INITIALS_STYLES else DEFAULT_INITIALS_STYLE
    if style == "first_name":
        return parts[0]
    if style == "last_name":
        return parts[-1]
    if style == "full_name":
        return " ".join(parts)
    return "".join(p[0].upper() for p in parts if p[0].isalpha()) or parts[0][0].upper()


_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "signatures", "fonts", "initials")

# id -> (label, TTF file in signatures/fonts/initials, or a ReportLab built-in name)
INITIALS_FONTS: dict[str, tuple[str, str]] = {
    "great-vibes": ("Great Vibes", "GreatVibes-Regular.ttf"),
    "allura": ("Allura", "Allura-Regular.ttf"),
    "sacramento": ("Sacramento", "Sacramento-Regular.ttf"),
    "alex-brush": ("Alex Brush", "AlexBrush-Regular.ttf"),
    "parisienne": ("Parisienne", "Parisienne-Regular.ttf"),
    "yellowtail": ("Yellowtail", "Yellowtail-Regular.ttf"),
    "homemade-apple": ("Homemade Apple", "HomemadeApple-Regular.ttf"),
    "mr-dafoe": ("Mr Dafoe", "MrDafoe-Regular.ttf"),
    "la-belle-aurore": ("La Belle Aurore", "LaBelleAurore.ttf"),
    "cedarville-cursive": ("Cedarville Cursive", "Cedarville-Cursive.ttf"),
    "kaushan-script": ("Kaushan Script", "KaushanScript-Regular.ttf"),
    "times-italic": ("Times Italic", "Times-Italic"),
    "helvetica-oblique": ("Helvetica Italic", "Helvetica-Oblique"),
}
DEFAULT_INITIALS_FONT = "great-vibes"


def initials_reportlab_font(font_id: str | None) -> str:
    """Register (once) and return the ReportLab font name for an initials font id."""
    font_id = font_id if font_id in INITIALS_FONTS else DEFAULT_INITIALS_FONT
    source = INITIALS_FONTS[font_id][1]
    if not source.endswith(".ttf"):
        return source
    name = f"Initials-{font_id}"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, os.path.join(_FONT_DIR, source)))
    return name


# --- Fitting text in a field box -------------------------------------------

BOX_PADDING_X = 4.0
MIN_FONT_SIZE = 4.0
# Share of the box height the text may use (handwriting fonts have tall ascenders).
HEIGHT_RATIO = 0.7


def fit_font_size(text: str, font_name: str, width: float, height: float, max_size: float | None = None) -> float:
    """Largest size (capped at max_size) at which `text` fits inside the box."""
    usable_w = max(1.0, width - 2 * BOX_PADDING_X)
    size = max(MIN_FONT_SIZE, height * HEIGHT_RATIO)
    if max_size:
        size = min(size, max_size)
    measured = stringWidth(text, font_name, size) if text else 0
    if measured > usable_w:
        size = max(MIN_FONT_SIZE, size * usable_w / measured)
    return size


def stamp_baseline(font_name: str, font_size: float, box_bottom_y: float, height: float) -> float:
    """Baseline that centres the glyphs vertically in a box (PDF bottom-left coords)."""
    ascent, descent = pdfmetrics.getAscentDescent(font_name, font_size)
    glyph_height = ascent - descent
    return box_bottom_y + (height - glyph_height) / 2 - descent


def stamp_x(text: str, font_name: str, font_size: float, x: float, width: float, align: str) -> float:
    if align == "center":
        return x + (width - stringWidth(text, font_name, font_size)) / 2
    return x + BOX_PADDING_X


def build_stamp_options(data: dict) -> dict:
    """Normalised signer choices stored on a SigningJob."""
    style = data.get("initials_style")
    font = data.get("initials_font")
    return {
        "timezone": normalize_timezone(data.get("timezone")),
        "initials_style": style if style in INITIALS_STYLES else DEFAULT_INITIALS_STYLE,
        "initials_font": font if font in INITIALS_FONTS else DEFAULT_INITIALS_FONT,
    }
