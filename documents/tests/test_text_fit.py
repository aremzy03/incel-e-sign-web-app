"""The fitting policy for replacements (documents/services/text_fit.py)."""

import pytest

from documents.services.text_fit import fit_text, validate_fit, wrap_words


def measure(text, size):
    """Every character is half the font size wide."""
    return len(text) * size * 0.5


def fit(left=100, right=200, bottom=0, align="left", anchor=None):
    return {"left": left, "right": right, "bottom": bottom, "align": align,
            "anchor": anchor if anchor is not None else {"left": left, "right": right, "center": (left + right) / 2}[align]}


def test_text_that_fits_keeps_its_size_and_anchor():
    layout = fit_text("abcd", 10, 700, fit(), measure)
    assert layout["mode"] == "fit" and layout["size"] == 10
    assert layout["lines"] == [("abcd", 100, 700)]


def test_right_and_centre_alignment_pin_the_end_and_middle():
    assert fit_text("abcd", 10, 700, fit(align="right"), measure)["lines"][0][1] == 180
    assert fit_text("abcd", 10, 700, fit(align="center"), measure)["lines"][0][1] == 140


def test_slightly_too_long_text_shrinks():
    # 21 chars * 5 = 105 > 100, but 90% would fit.
    layout = fit_text("a" * 21, 10, 700, fit(bottom=690), measure)
    assert layout["mode"] == "shrink"
    assert measure("a" * 21, layout["size"]) <= 100


def test_much_longer_text_wraps_when_there_is_room_below():
    layout = fit_text("aaaa bbbb cccc dddd eeee ffff", 10, 700, fit(right=150, bottom=600), measure)
    assert layout["mode"] == "wrap" and layout["size"] == 10
    assert [line for line, _x, _y in layout["lines"]] == ["aaaa bbbb", "cccc dddd", "eeee ffff"]
    assert [y for _l, _x, y in layout["lines"]] == [700, 688, 676]


def test_no_room_below_shrinks_down_to_three_quarters_then_overflows():
    no_room = fit(right=150, bottom=699)
    assert fit_text("a" * 12, 10, 700, no_room, measure)["mode"] == "shrink"  # 60 -> 50 is 83%
    layout = fit_text("a" * 30, 10, 700, no_room, measure)
    assert layout["mode"] == "overflow" and layout["overflow"] and layout["size"] == 7.5


def test_a_word_wider_than_the_slot_does_not_wrap():
    assert wrap_words("short " + "x" * 40, 10, 100, measure) is None


@pytest.mark.parametrize(
    "value, ok",
    [
        (None, True),
        ({"left": 72, "right": 300, "bottom": 650, "align": "left", "anchor": 72}, True),
        ({"left": 72, "right": 300, "bottom": 650, "align": "justify", "anchor": 72}, False),
        ({"left": 300, "right": 72, "bottom": 650, "align": "left", "anchor": 72}, False),
        ({"left": 72, "right": 300, "bottom": 750, "align": "left", "anchor": 72}, False),
        ({"left": 72, "right": 300, "bottom": 10, "align": "left", "anchor": 72}, False),
        ({"left": 72, "right": 900, "bottom": 650, "align": "left", "anchor": 72}, False),
        ({"left": "x", "right": 300, "bottom": 650, "align": "left", "anchor": 72}, False),
    ],
)
def test_validate_fit(value, ok):
    assert validate_fit(value, baseline_y=700, font_size=12, page_width=612, page_height=792, tolerance=1) is ok
