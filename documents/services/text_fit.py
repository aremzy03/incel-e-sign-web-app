"""
Fit a replacement into the space its original text had (plan-full-text-rewrite, "Borders and alignment").

The editor works out each run's slot from the page: the borders, the neighbouring
words and the page margins on either side, how far down it may wrap, and whether the
text is left-, right- or centre-aligned. It sends that as the op's ``fit``:

    {"left": x, "right": x, "bottom": y, "align": "left" | "center" | "right", "anchor": x}

in PDF user space (bottom-left origin). ``anchor`` is where the text is pinned: its
start (left), end (right) or middle (center).

The policy, the same on both sides (lib/pdf-edit/text-fit.ts mirrors it):

1. It fits: one line at the original size.
2. It nearly fits (at 90% or more): one line, shrunk to fit.
3. It fits wrapped onto lines below, inside the slot and above ``bottom``: wrapped.
4. It fits at 75% or more: one line, shrunk to fit.
5. Otherwise one line at 75%, marked as overflowing (the editor warns): it overlaps as little as it can.
"""

from __future__ import annotations

from typing import Callable

LINE_HEIGHT = 1.2
NEAR_FIT_SCALE = 0.9
MIN_FIT_SCALE = 0.75
MAX_WRAP_LINES = 20
# Below the last baseline the descenders need room too.
DESCENT = 0.25
ALIGNS = ("left", "center", "right")

Measure = Callable[[str, float], float]


def _available(fit: dict) -> float:
    left, right, anchor = float(fit["left"]), float(fit["right"]), float(fit["anchor"])
    align = fit["align"]
    if align == "right":
        return anchor - left
    if align == "center":
        return 2 * min(anchor - left, right - anchor)
    return right - anchor


def _line_x(fit: dict, width: float) -> float:
    anchor = float(fit["anchor"])
    if fit["align"] == "right":
        return anchor - width
    if fit["align"] == "center":
        return anchor - width / 2
    return anchor


def wrap_words(text: str, size: float, width: float, measure: Measure) -> list[str] | None:
    """Greedy word wrap; None when one word alone is wider than the line."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if measure(word, size) > width:
            return None
        candidate = f"{current} {word}" if current else word
        if current and measure(candidate, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _shrunk(natural: float, available: float, size: float) -> float:
    # Rounded down to 0.01pt so the result stays inside the slot.
    return int(size * available / natural * 100) / 100


def fit_text(text: str, size: float, baseline_y: float, fit: dict, measure: Measure, *, allow_wrap: bool = True) -> dict:
    """
    Lay ``text`` out in its slot. Returns ``{"mode", "size", "lines": [(text, x, baseline_y)], "overflow"}``
    with mode one of "fit", "shrink", "wrap", "overflow".
    """
    available = max(_available(fit), 0.0)
    text = text.strip()
    natural = measure(text, size)

    def single(mode: str, line_size: float) -> dict:
        width = measure(text, line_size)
        return {
            "mode": mode,
            "size": line_size,
            "lines": [(text, _line_x(fit, width), baseline_y)],
            "overflow": mode == "overflow",
        }

    if natural <= available + 0.01:
        return single("fit", size)
    if natural * NEAR_FIT_SCALE <= available:
        return single("shrink", _shrunk(natural, available, size))
    if allow_wrap:
        lines = wrap_words(text, size, available, measure)
        if lines and 1 < len(lines) <= MAX_WRAP_LINES:
            step = LINE_HEIGHT * size
            last_baseline = baseline_y - (len(lines) - 1) * step
            if last_baseline - DESCENT * size >= float(fit["bottom"]) - 0.01:
                return {
                    "mode": "wrap",
                    "size": size,
                    "lines": [
                        (line, _line_x(fit, measure(line, size)), baseline_y - index * step)
                        for index, line in enumerate(lines)
                    ],
                    "overflow": False,
                }
    if natural * MIN_FIT_SCALE <= available:
        return single("shrink", _shrunk(natural, available, size))
    return single("overflow", int(size * MIN_FIT_SCALE * 100) / 100)


def validate_fit(fit, *, baseline_y: float, font_size: float, page_width: float, page_height: float, tolerance: float) -> bool:
    """True when ``fit`` is absent or well formed and on the page."""
    if fit is None:
        return True
    if not isinstance(fit, dict) or fit.get("align") not in ALIGNS:
        return False
    try:
        left, right = float(fit["left"]), float(fit["right"])
        bottom, anchor = float(fit["bottom"]), float(fit["anchor"])
    except (KeyError, TypeError, ValueError):
        return False
    values = (left, right, bottom, anchor)
    if any(value != value or value in (float("inf"), float("-inf")) for value in values):
        return False
    return (
        -tolerance <= left < right <= page_width + tolerance
        and left - tolerance <= anchor <= right + tolerance
        and -tolerance <= bottom <= baseline_y + tolerance
        # No deeper than the wrap limit allows.
        and baseline_y - bottom <= (MAX_WRAP_LINES * LINE_HEIGHT + 1) * font_size
        and baseline_y <= page_height + tolerance
    )
