"""Now's extras from the grind tracker: about how many kills to the next level, and a note when the
EXP stops coming while you're still on the map you were grinding."""
from test_grind import NEED, feed, tracker


def test_kills_left_at_the_usual_kill(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    t = feed(g, [51900 + 200], t0=t)            # one read caught two kills: the usual kill is still 100
    s = g.summary(t)
    assert s["per_kill"] == 100
    assert s["kills_left"] == -(-(NEED - 52100) // 100)


def test_no_kill_count_from_a_handful(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(4)])
    assert g.summary(t)["kills_left"] is None


def test_a_minute_without_exp_after_grinding_is_noted(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(60)])      # six minutes of grinding
    assert not g.summary(t)["stalled"]
    t = feed(g, [55900] * 11, t0=t)                         # then 66 s with nothing
    s = g.summary(t)
    assert s["stalled"] and s["stalled_s"] >= 60


def test_no_note_after_a_short_try_or_on_a_new_map(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])      # two minutes only
    t = feed(g, [51900] * 11, t0=t)
    assert not g.summary(t)["stalled"]
    t = feed(g, [52000 + 100 * i for i in range(60)], t0=t)
    t = feed(g, [57900] * 11, t0=t, map_id=2, name="Ant Tunnel II")   # walked on: a new map, a new start
    assert not g.summary(t)["stalled"]


def test_paused_never_notes(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(60)])
    g.pause(True)
    t = feed(g, [55900] * 11, t0=t)
    assert not g.summary(t)["stalled"]
