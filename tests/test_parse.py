"""Small parsing helpers of the reader, on text as Windows OCR really gives it."""
import pytest

import reader


@pytest.mark.parametrize("text,expected", [
    ("152 (142+10)", (152, 142)),
    ("1 52 (1 42+1 0)", (152, 142)),     # OCR puts a space after every 1
    ("32 (30+2)", (32, 30)),
    ("4", (4, 4)),
    ("", (None, None)),
])
def test_stat_number(text, expected):
    assert reader.stat_number(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Quest Helper (4/5)", 4), ("Quest Helper (4 / 5)", 4), ("Quest Helper (4.15)", 4), ("Quest Helper", None),
])
def test_helper_count(text, expected):
    assert reader.helper_count(text) == expected


@pytest.mark.parametrize("nums,need,expected", [
    ("5", 25, None),        # "0 / 25" with "0 / 2" behind a rope: not a count of 5
    ("0/", 1, 0), ("3 25", 25, 3), ("30130", 30, 30), ("1", 1, None), ("12 / 30", 30, 12),
])
def test_count_needs_its_goal_in_view(nums, need, expected):
    assert reader._have(nums, need) == expected


def test_slash_read_as_backslash_is_a_count():
    line = "1 " + chr(92) + " 1 Omok Piece: Pig"          # "1 / 1" with the slash read as a backslash
    m = reader.PROGRESS.match(reader._count_text(line))
    assert m and m.group(2) == "Omok Piece: Pig"
    assert reader._have(m.group(1), 1) == 1


def test_more_titles_than_tracked_keeps_the_best_read_in_screen_order():
    qs = [{"quest": "Make a Pig & Octopus Omok Set", "score": 95}, {"quest": "Make a Slime & Octopus Omok Set", "score": 87},
          {"quest": "The Filing Error", "score": 100}]
    assert [q["quest"] for q in reader.cap_quests(qs, 2)] == ["Make a Pig & Octopus Omok Set", "The Filing Error"]
    assert reader.cap_quests(qs, None) == qs and reader.cap_quests(qs, 3) == qs


def test_cut_name_that_fits_two_is_not_guessed():
    lines = ["Caretaker's Ledger", "Maple World's Unique Fun: Match Cards", "Maple World's Unique Fun: Omok"]
    assert reader.match_quest("Maple World's Unique Fun:...", lines) is None
    assert reader.match_quest("Caretaker's Led...", lines) == "Caretaker's Ledger"


SCROLLS = ["Hat Accuracy Scroll: Greater", "Hat Accuracy Scroll: Intermediate", "Hat Accuracy Scroll: Basic",
           "Earring INT Scroll: Intermediate", "Earring INT Scroll: Greater", "Horny Mushroom Cap"]


@pytest.mark.parametrize("text,expected", [
    ("Hat Accuracy Scroll: Inter...", "Hat Accuracy Scroll: Intermediate"),
    ("Earring INT Scroll: Interm...", "Earring INT Scroll: Intermediate"),
    ("Horny Mushroom Cap", "Horny Mushroom Cap"),
    ("Hat Accuracy Scroll: ...", None),          # three grades start so: not guessed
])
def test_shop_item_name(text, expected):
    assert reader.match_item(text, SCROLLS) == expected


def _stem(flag):
    """A 2 px wide stem, 14 px tall; with `flag`, the 1's flag 2 px to its left in its top rows."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (20, 18), (230, 230, 225))
    d = ImageDraw.Draw(img)
    d.rectangle((10, 2, 11, 15), fill=(20, 20, 20))
    if flag:
        d.rectangle((7, 3, 9, 4), fill=(20, 20, 20))
    return img


def test_a_straight_stem_is_an_l():
    assert reader.fix_one_vs_l("l", _stem(False)) == "l"


def test_a_stem_with_a_flag_is_a_1():
    assert reader.fix_one_vs_l("l", _stem(True)) == "1"


def test_the_name_tura1_on_the_stat_window():
    from casekit import CASES
    from PIL import Image
    if not (CASES / "fm_quest_window.png").exists():
        pytest.skip("no cases on this PC")
    crop = Image.open(CASES / "fm_quest_window.png").convert("RGB").crop((856, 700, 1008, 720))
    assert reader.fix_one_vs_l("Tural", crop) == "Tura1"


def test_a_name_that_cant_be_checked_is_not_guessed():
    from PIL import Image
    covered = Image.new("RGB", (60, 18), (40, 40, 90))          # under a tooltip's dark navy
    assert reader.fix_one_vs_l("Tural", covered) is None        # its "l" could be a 1
    assert reader.fix_one_vs_l("Bob", covered) == "Bob"         # nothing a 1 could hide in


# The mini map's name line can come back from OCR as two pieces on one row ("Kerning" | "City",
# "1st Accornpanijnent" | "<2nd Stage>"); sorted top to bottom, the one a pixel lower came last
# and was read alone (2026-11-08). (text, x, y, w, h)
@pytest.mark.parametrize("lines,expected", [
    ([("Victoria Road", 100, 40, 90, 12), ("City", 170, 59, 30, 12), ("Kerning", 100, 60, 60, 12)],
     ("Victoria Road", "Kerning City")),
    ([("Hidden Street", 100, 40, 90, 12), ("<2nd Stage>", 230, 59, 70, 12), ("1st Accornpanijnent", 100, 60, 120, 12)],
     ("Hidden Street", "1st Accornpanijnent <2nd Stage>")),
    ([("Victoria Road", 100, 40, 90, 12), ("Kerning City", 100, 60, 85, 12)], ("Victoria Road", "Kerning City")),
    ([("Kerning City", 100, 60, 85, 12)], (None, "Kerning City")),
    ([], (None, None)),
])
def test_title_lines_join_the_pieces_of_a_row(lines, expected):
    assert reader.title_lines(lines) == expected
