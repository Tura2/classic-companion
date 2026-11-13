"""The game's bottom-right corner lines (EXP, mesos and items picked up) as events, each counted
once though a line stays several reads and scrolls up as new ones come."""
import notices

NAMES = ["Tree Branch", "Squishy Liquid", "Tablecloth"]


def test_parse_the_three_kinds():
    assert notices.parse("You received EXP (+66)", NAMES) == ("exp", 66)
    assert notices.parse("You received EXP (+66) (+13)", NAMES) == ("exp", 79)
    assert notices.parse("You have gained mesos (+15)", NAMES) == ("mesos", 15)
    assert notices.parse("Tree Branch x1 earned. (Etc)", NAMES) == ("item", "Tree Branch", 1)
    assert notices.parse("Squishy Liquid x12 earned (Etc)", NAMES) == ("item", "Squishy Liquid", 12)
    assert notices.parse("Buddy: hi", NAMES) is None


def test_an_unknown_item_keeps_no_name():
    assert notices.parse("Shiny Rock x1 earned. (Etc)", NAMES) == ("item", None, 1)


def test_a_line_still_shown_counts_once():
    tr = notices.Tracker()
    assert tr.update([("You have gained mesos (+15)", 500)], 13, NAMES) == [("mesos", 15)]
    assert tr.update([("You have gained mesos (+15)", 500)], 13, NAMES) == []          # same, not moved
    got = tr.update([("You have gained mesos (+15)", 487), ("You received EXP (+66)", 500)], 13, NAMES)
    assert got == [("exp", 66)]                                                          # it scrolled up one row


def test_identical_lines_count_by_their_shift():
    tr = notices.Tracker()
    tr.update([("You received EXP (+66)", 500)], 13, NAMES)
    got = tr.update([("You received EXP (+66)", 487), ("You received EXP (+66)", 500)], 13, NAMES)
    assert got == [("exp", 66)]


def test_lines_fading_off_the_top_are_not_new():
    tr = notices.Tracker()
    tr.update([("You received EXP (+66)", 487), ("You have gained mesos (+15)", 500)], 13, NAMES)
    assert tr.update([("You have gained mesos (+15)", 500)], 13, NAMES) == []


def test_an_empty_read_forgets_the_stack():
    tr = notices.Tracker()
    tr.update([("You have gained mesos (+15)", 500)], 13, NAMES)
    tr.update([], 13, NAMES)
    assert tr.update([("You have gained mesos (+15)", 500)], 13, NAMES) == [("mesos", 15)]
