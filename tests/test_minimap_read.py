"""The mini map's title read close up from more than one picture of it (reader.read_title), the quick
look at just the mini map between full reads (Reader.read_map_only), and what such a look changes in
the app (sniper.App.apply_seen)."""
from types import SimpleNamespace

import pytest
from PIL import Image

from casekit import CASES

import reader
import sniper
from gamedata import MapMove

BOX = (0, 0, 300, 60)


def ocr_by_prep(monkeypatch, said):
    """read_box stands in for OCR: each picture of the title "reads" as `said[prep]` (rows of text)."""
    asked = []

    def fake(frame, box, s=1.0, pad=0, prep=None):
        asked.append(prep)
        return [(text, 0, 20 * i, 200, 14) for i, text in enumerate(said.get(prep, []))]
    monkeypatch.setattr(reader, "read_box", fake)
    return asked


def test_the_map_two_pictures_agree_on(monkeypatch, game_reader):
    asked = ocr_by_prep(monkeypatch, {"white": ["Victoria Road", "West Rocky Mountain IV"],
                                      "bright": ["Victoria Road", "West Rocky Mountain IV"],
                                      None: ["Victoria Road"]})
    street, name, _, _ = reader.read_title(None, BOX, 1.0, game_reader.map_names, game_reader.street_names)
    assert (street, name) == ("Victoria Road", "West Rocky Mountain IV")
    assert asked == ["white", "bright"]          # two agree: no third read


def test_gray_alone_still_counts(monkeypatch, game_reader):
    ocr_by_prep(monkeypatch, {"white": ["Vict"], "bright": [], None: ["Victoria Road", "Ant Tunnel I"]})
    assert reader.read_title(None, BOX, 1.0, game_reader.map_names, game_reader.street_names)[1] == "Ant Tunnel I"


def test_a_cut_numeral_loses_to_two_whole_reads(monkeypatch, game_reader):
    # the bright picture drops the V: "West Rocky Mountain I" is a real map too, but the other two agree
    ocr_by_prep(monkeypatch, {"white": ["Victoria Road", "West Rocky Mountain IV"],
                              "bright": ["Victoria Road", "West Rocky Mountain I"],
                              None: ["Victoria Road", "West Rocky Mountain IV"]})
    assert reader.read_title(None, BOX, 1.0, game_reader.map_names, game_reader.street_names)[1] == "West Rocky Mountain IV"


def test_no_map_gives_the_last_row_for_the_log(monkeypatch, game_reader):
    ocr_by_prep(monkeypatch, {"white": ["Victoria Road"], "bright": ["Victoria Road"], None: ["Victoria Road"]})
    street, name, lines, last = reader.read_title(None, BOX, 1.0, game_reader.map_names, game_reader.street_names)
    assert (street, name, lines, last) == (None, None, None, "Victoria Road")


@pytest.mark.skipif(not (CASES / "minimap_light_bg.png").exists(), reason="no cases on this PC")
def test_map_only_look_reads_the_mini_map_where_it_was(game_reader):
    frame = Image.open(CASES / "minimap_light_bg.png").convert("RGB")
    game_reader.titles.last, game_reader.reads = {}, 0
    assert game_reader.read_map_only(frame) is None          # its place isn't known yet
    game_reader.read(frame)                                  # a full read finds it
    seen = game_reader.read_map_only(frame)
    assert seen["map_only"] and seen["quick"]
    assert (seen["map"]["street"], seen["map"]["name"]) == ("Victoria Road", "West Rocky Mountain IV")


def test_a_map_only_look_moves_you_and_touches_nothing_else(game_reader):
    data = game_reader.data
    cur, new = data.match_map_name("West Rocky Mountain III"), data.match_map_name("West Rocky Mountain IV")
    moved = []
    a = SimpleNamespace(state={"profile": {"current_map": cur, "level": 37}, "nav": None, "set_current": moved.append},
                        data=data, map_move=MapMove(), mini=None, mini_next=None, bounds=None, drawing=lambda: False)
    a.apply_map = lambda seen, prof: sniper.App.apply_map(a, seen, prof)
    seen = {"map_only": True, "quick": True, "windows": {}, "scale": 1.0,
            "map": {"street": "Victoria Road", "name": "West Rocky Mountain IV", "title": [0, 0, 1, 1], "collapsed": False}}
    need = data.reads_to_move(cur, new)
    for i in range(need):
        assert moved == []
        sniper.App.apply_seen(a, dict(seen), None)
    assert moved == [new]
    assert a.state["game"]["map"]["id"] == new
    assert set(a.state) == {"profile", "nav", "set_current", "game"}    # no store, no frame, nothing else
