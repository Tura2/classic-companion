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


# Read in Kerning PQ on 2026-11-08 (Companion's "not recognised" log): the stage word is mangled and
# the "<" often lost, so the stage is told by its ordinal's ending (st/nd/rd/th) or "last".
@pytest.mark.parametrize("text, want", [
    ("1st Accornpanijnent cist Stag", "1st Accompaniment <1st Stage>"),
    ("1st Accornpanijnent cist Stage>", "1st Accompaniment <1st Stage>"),
    ("1st Accojnpanirnent end Stage?", "1st Accompaniment <2nd Stage>"),
    ("1st Accornpanijnent Ord Stage>", "1st Accompaniment <3rd Stage>"),
    ("1st Accompanirnent <4tIi stage>", "1st Accompaniment <4th stage>"),
    ("1st Accompanirnent <4tIi stage> I", "1st Accompaniment <4th stage>"),
    ("1st Accompanirnent <4tIi stage>l", "1st Accompaniment <4th stage>"),
    ("1st Accompaniment <4tIi stage", "1st Accompaniment <4th stage>"),
    ("1st Accornpanijnent <4tIi stag", "1st Accompaniment <4th stage>"),
    ("1st Accornpanijnent <4tIi stage>", "1st Accompaniment <4th stage>"),
])
def test_kpq_stage_titles_mangled_in_a_live_run(text, want):
    assert match_place(text, KPQ, 86) == want


@pytest.mark.parametrize("text", ["1st Accornpanijnent", "1 st Accompaniment", "Kerning Ciy <2nd Stage>"])
def test_a_title_without_its_stage_names_no_stage(text):
    assert match_place(text, KPQ, 86) is None


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
