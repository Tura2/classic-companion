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
