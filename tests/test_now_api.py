"""Now's data: the corner's lines feed the grind session (named kills, loot, mesos), and what the
dashboard gets for it: the session with each monster and each item's tooltip, the last session,
whether you're in a town, and every map's rates."""
from types import SimpleNamespace

import companion
import grind
import sniper


def app(tmp_path, data):
    return SimpleNamespace(grind=grind.Grind(tmp_path / "grind.sqlite"), data=data)


def reads(a, prof, exp, lines=(), n=3):
    """A few full reads showing HUD EXP `exp`, then the corner's new lines (notices.Corner's events)."""
    seen = {"hud": {"exp": exp, "exp_pct": round(exp / 1227.55, 2)}}
    for _ in range(n):
        sniper.handle_grind(a, seen, prof)
    sniper.handle_corner(a, list(lines))


def test_exp_lines_become_named_kills(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [])
    reads(a, prof, 50066, [("exp", 66)])
    reads(a, prof, 50137, [("exp", 71)])
    s = a.grind.summary(1e10)
    assert s["kills"] == [{"name": "Jr. Wraith", "count": 1}, {"name": None, "count": 1}]


def test_items_and_mesos_from_lines(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [("item", "Tablecloth", 1), ("mesos", 15), ("item", "Tablecloth", 2), ("party", 3)])
    s = a.grind.summary(1e10)
    assert s["loot"] == [{"name": "Tablecloth", "count": 3}] and s["mesos_picked"] == 15


def test_used_events_reach_the_session(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [("used", "Orange Potion", 2), ("used", None, 1)])
    assert a.grind.summary(1e10)["used"] == [{"name": "Orange Potion", "count": 2}]


def test_an_item_line_naming_no_item_is_not_loot(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [("item", None, 1)])
    assert a.grind.summary(1e10)["loot"] == []


def test_a_maps_drops_by_name(game_reader):
    d = game_reader.data
    drops = d.map_drop_names(d.match_map_name("West Rocky Mountain IV"))
    assert "Wild Boar Tooth" in drops
    assert d.map_drop_names(None) == set()


def test_session_view_has_monsters_and_tooltip_fields(tmp_path, game_reader):
    d = game_reader.data
    line2 = d.match_map_name("Line 2 <Area 1>")
    g = grind.Grind(tmp_path / "grind.sqlite")
    g.add_kill("Jr. Wraith", 0)
    g.add_loot("Tablecloth", 3, 0)
    v = companion.session_view(g, d, line2, 100)
    wraith = next(k for k in v["kills"] if k["name"] == "Jr. Wraith")
    assert (wraith["count"], wraith["hp"], wraith["exp"], wraith["level"]) == (1, 982, 66, 34) and wraith["img"]
    assert next(k for k in v["kills"] if k["name"] == "Jr. Necki")["count"] == 0       # on the map, not killed yet
    cloth = v["loot"][0]
    assert (cloth["name"], cloth["count"], cloth["kind"]) == ("Tablecloth", 3, "Etc")
    assert cloth["desc"].startswith("A tablecloth") and cloth["img"] and "msc" in cloth and "npc" in cloth


def test_session_view_nets_loot_and_used(tmp_path, game_reader):
    d = game_reader.data
    g = grind.Grind(tmp_path / "grind.sqlite")
    g.add_loot("Orange Potion", 1, 0)
    g.add_used("Orange Potion", 12, 0)
    g.add_loot("Tablecloth", 3, 0)
    g.add_used("Blue Potion", 9, 0)
    g.add_used("White Potion", 2, 0)
    g.add_loot("White Potion", 2, 0)
    loot = companion.session_view(g, d, None, 100)["loot"]
    assert [x["name"] for x in loot] == ["Tablecloth", "Orange Potion", "Blue Potion", "White Potion"]
    assert [x["count"] for x in loot] == [3, -11, -9, 0]
    orange, blue = loot[1], loot[2]
    assert (orange["picked"], orange["used"]) == (1, 12) and (loot[0]["picked"], loot[0]["used"]) == (3, 0)
    assert blue["img"] and blue["kind"] == "Use" and "msc" in blue and "npc" in blue


def test_town_with_keep_counting_shows_this_session(tmp_path, game_reader):
    d = game_reader.data
    g = grind.Grind(tmp_path / "grind.sqlite")
    g.no_reset = True
    kc, line2 = d.match_map_name("Kerning City"), d.match_map_name("Line 2 <Area 1>")
    for i, exp in enumerate([50000] * 3 + [50066] * 3):          # three reads agree before a level's EXP counts
        g.update(exp, round(exp / 1227.55, 2), 32, line2, "Line 2 <Area 1>", i * 3)
    g.update(50066, round(50066 / 1227.55, 2), 32, kc, "Kerning City", 20)
    v = companion.grind_view(g, d, {"current_map": kc, "level": 32}, 30)
    assert v["town"] is True and v["keep"] is True and v["session"]["gain_pct"] > 0


def test_town_without_keep_has_the_last_session(tmp_path, game_reader):
    d = game_reader.data
    g = grind.Grind(tmp_path / "grind.sqlite")
    kc, line2 = d.match_map_name("Kerning City"), d.match_map_name("Line 2 <Area 1>")
    for i, exp in enumerate([50000] * 3 + [50066] * 3):          # three reads agree before a level's EXP counts
        g.update(exp, round(exp / 1227.55, 2), 32, line2, "Line 2 <Area 1>", i * 3)
    g.update(50066, round(50066 / 1227.55, 2), 32, kc, "Kerning City", 20)
    v = companion.grind_view(g, d, {"current_map": kc, "level": 32}, 30)
    assert v["town"] is True and v["keep"] is False and v["last"]["map"] == "Line 2 <Area 1>"


def test_the_view_says_whether_the_corner_is_read(tmp_path, game_reader):
    import reader
    g = grind.Grind(tmp_path / "grind.sqlite")
    v = companion.grind_view(g, game_reader.data, {"current_map": game_reader.data.match_map_name("Line 2 <Area 1>"), "level": 32}, 30)
    assert v["corner"] is reader.CORNER_READ


def test_hud_gains_become_named_kills(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [])
    reads(a, prof, 50066, [])
    reads(a, prof, 50171, [])                     # +105: a Jr. Wraith and a Jr. Necki
    reads(a, prof, 50242, [])                     # +71: nothing here gives that
    kills = {k["name"]: k["count"] for k in a.grind.summary(1e10)["kills"]}
    assert kills["Jr. Wraith"] == 2 and kills["Jr. Necki"] == 1 and kills[None] >= 1


def test_corner_exp_lines_are_not_counted_twice(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("Line 2 <Area 1>"), "level": 32}
    reads(a, prof, 50000, [])
    reads(a, prof, 50066, [("exp", 66)])
    assert a.grind.summary(1e10)["kills"] == [{"name": "Jr. Wraith", "count": 1}]


def test_party_gains_become_your_kills_and_your_partys(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("West Rocky Mountain IV"), "level": 37}
    exp = 166000
    reads(a, prof, exp, [])
    for gain in [62, 43, 46, 31, 31, 20, 31, 51, 30, 31, 21, 62, 31, 20, 44, 31]:      # read live, two players
        exp += gain
        reads(a, prof, exp, [])
    s = a.grind.summary(1e10)
    yours = {k["name"]: k["count"] for k in s["kills"]}
    party = {k["name"]: k["count"] for k in s["party_kills"]}
    assert yours.get("Wild Boar", 0) >= 10 and party.get("Wild Boar", 0) >= 2
    assert None not in yours or yours[None] <= 2           # nearly every gain told, not left unnamed
    v = companion.session_view(a.grind, d, prof["current_map"], 1e10)
    boar = next(k for k in v["kills"] if k["name"] == "Wild Boar")
    assert boar["party"] == party["Wild Boar"]
