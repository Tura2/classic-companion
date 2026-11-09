"""Telling a real map change from a misread mini map title (2026-11-09, East Rocky Mountain VI):
the title flipped to "Victoria Road" (its street line read alone) and to "East Rocky Mountain VII"
(a stray stroke after the numeral) every 5-30 s; each flip started Grind's numbers over and
re-planned the route, once into an 18-step detour through Henesys."""
import gamedata
import reader

VI, VII, V, ROAD, PERION, HENESYS = 55, 56, 54, 8, 40, 10


def bare():
    g = object.__new__(gamedata.GameData)
    g.maps = {i: {"id": i, "name": n, "street_name": st} for i, n, st in [
        (VI, "East Rocky Mountain VI", "Victoria Road"), (VII, "East Rocky Mountain VII", "Victoria Road"),
        (V, "East Rocky Mountain V", "Victoria Road"), (PERION, "Perion", "Victoria Road"),
        (HENESYS, "Henesys", "Victoria Road"),
        (ROAD, "Victoria Road", "Yellow Mushroom House")]}       # the game data has these two swapped
    g.graph = {V: {VI: {}}, VI: {V: {}, VII: {}}, VII: {VI: {}}, ROAD: {HENESYS: {}}, HENESYS: {ROAD: {}}}
    return g


# ---- the street line read without the name under it
NAMES = ["East Rocky Mountain VI", "East Rocky Mountain VII", "Victoria Road", "Perion", "Henesys"]
STREETS = {"Victoria Road", "Yellow Mushroom House"}


def test_a_lone_street_line_names_no_map():
    assert reader.title_map(None, "Victoria Road", NAMES, STREETS) is None
    assert reader.title_map(None, "Victoria Roa", NAMES, STREETS) is None


def test_the_name_under_the_street_still_reads():
    assert reader.title_map("Victoria Road", "East Rocky Mountain VI", NAMES, STREETS) == "East Rocky Mountain VI"
    assert reader.title_map("Victoria Road", "Perion", NAMES, STREETS) == "Perion"


def test_a_lone_name_line_still_reads():
    assert reader.title_map(None, "Perion", NAMES, STREETS) == "Perion"


# ---- how many reads in a row a move needs
def test_a_portal_away_needs_two_reads():
    assert bare().reads_to_move(HENESYS, ROAD) == 2


def test_a_map_one_stroke_off_needs_four():
    g = bare()
    assert g.reads_to_move(VI, VII) == 4          # VI -> VII: a stray stroke reads the same
    assert g.reads_to_move(VII, VI) == 4
    assert g.reads_to_move(V, VI) == 4             # V -> VI is the same extra stroke


def test_a_map_far_away_needs_three():
    assert bare().reads_to_move(VI, PERION) == 3  # a return scroll, a taxi, or a misread


def test_unknown_current_map_needs_two():
    assert bare().reads_to_move(None, PERION) == 2


def test_the_moves_rule():
    g, mv = bare(), gamedata.MapMove()
    seq = [VII, VII, VI, VII, VII, VII]             # misreads two or three in a row never move you
    assert [mv.read(g, VI, x) for x in seq] == [False] * 6
    assert mv.read(g, VI, VII) is True              # a fourth in a row: you really walked over
    assert [gamedata.MapMove().read(g, VI, x) for x in [VII] * 3] == [False] * 3


def test_a_read_of_where_you_are_breaks_the_streak():
    g, mv = bare(), gamedata.MapMove()
    assert [mv.read(g, HENESYS, x) for x in [ROAD, HENESYS, ROAD, ROAD]] == [False, False, False, True]


def test_unread_titles_dont_break_the_streak():
    g, mv = bare(), gamedata.MapMove()
    assert [mv.read(g, VI, x) for x in [PERION, None, PERION, PERION]] == [False, False, False, True]
