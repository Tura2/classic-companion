"""The history card as the pop-up gets it: pictures for monsters and items, names kept when unknown."""
import companion
import grind
from test_grind import feed


def test_card_view_resolves_pictures_and_keeps_unknown_names(tmp_path, game_reader):
    d = game_reader.data
    g = grind.Grind(tmp_path / "grind.sqlite")
    mid = d.match_map_name("Line 2 <Area 1>")
    g.who = {"name": "Tura1", "job": "Hunter"}
    t = feed(g, [50000 + 100 * i for i in range(41)], map_id=mid, name="Line 2 <Area 1>")
    for _ in range(3):
        g.add_kill("Jr. Wraith", t)
    g.add_kill("Gone Monster", t)
    g.add_kill(None, t); g.add_kill(None, t)
    g.add_loot("Tablecloth", 2, t)
    g.add_loot("Gone Item", 1, t)
    g.close(t)
    card = g.history_card("h1")
    v = companion.card_view(card, d)
    kills = {k["name"]: k for k in v["kills"]}
    assert kills["Jr. Wraith"]["img"] and kills["Jr. Wraith"]["count"] == 3
    assert kills["Gone Monster"]["img"] is None and kills[None]["img"] is None and kills[None]["count"] == 2
    loot = {x["name"]: x for x in v["loot"]}
    assert loot["Tablecloth"]["img"] and loot["Tablecloth"]["count"] == 2
    assert loot["Gone Item"]["img"] is None and loot["Gone Item"]["count"] == 1
    assert v["best_minute"] == max(card["minutes"]["vals"])
