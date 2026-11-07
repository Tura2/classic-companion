"""Mini map titles to map names: the number part must match, loosely enough for OCR's misreads."""
import pytest

from gamedata import match_place

KPQ = ["1st Accompaniment <1st Stage>", "1st Accompaniment <2nd Stage>", "1st Accompaniment <3rd Stage>",
       "1st Accompaniment <4th stage>", "1st Accompaniment <Last Stage>", "1st Accompaniment <Bonus>",
       "Kerning City"]
OTHERS = ["Ant Tunnel I", "Ant Tunnel II", "Line 1 <Area 1>", "Line 1 <Area 2>", "Line 1 <Area 3>",
          "Free Market <1>", "Free Market <7>", "Free Market <17>"]


@pytest.mark.parametrize("text, want", [
    ("Ist Accompaniment <Ist Stage>", "1st Accompaniment <1st Stage>"),
    ("1st Accompaniment <1 st Stage>", "1st Accompaniment <1st Stage>"),
    ("lst Accompaniment <1st Stage>", "1st Accompaniment <1st Stage>"),
    ("1st Accompaniment <2nd Stage)", "1st Accompaniment <2nd Stage>"),
    ("1st Accompaniment <3rd Stage", "1st Accompaniment <3rd Stage>"),
    ("1st Accompaniment <4th Stage>", "1st Accompaniment <4th stage>"),
    ("Ist Accompaniment <Last Stage>", "1st Accompaniment <Last Stage>"),
])
def test_kpq_stage_titles_as_ocr_reads_them(text, want):
    assert match_place(text, KPQ, 86) == want


@pytest.mark.parametrize("text, want", [
    ("Ant Tunnel Il", "Ant Tunnel II"),
    ("Ant Tunnel I", "Ant Tunnel I"),
    ("Line 1 <Area 3>", "Line 1 <Area 3>"),
    ("Line 1 <Area 2)", "Line 1 <Area 2>"),
    ("Free Market <7>", "Free Market <7>"),
    ("Free Market <1>", "Free Market <1>"),
])
def test_numbered_maps_still_land_on_their_own_number(text, want):
    assert match_place(text, OTHERS, 86) == want
