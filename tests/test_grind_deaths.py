"""Deaths in the grind tracker: a confirmed EXP drop of up to 10% of the level's EXP is a death
(LUK lowers the loss; a Safety Charm or a town death costs nothing and can't be seen), counted net
in everything that uses EXP. A bigger drop, or one read alone, is still a misread."""
from test_grind import NEED, feed, pct, tracker


def test_a_ten_percent_drop_is_a_death(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])            # grinding
    t = feed(g, [51900 - round(NEED * 0.10)], t0=t)              # two reads agree on the drop
    s = g.summary(t)
    assert [d["lost"] for d in s["deaths"]] == [round(NEED * 0.10)] and s["exp_lost"] == round(NEED * 0.10)
    assert s["gained"] == 1900 - round(NEED * 0.10)              # net


def test_a_smaller_drop_is_a_death_too(tmp_path):                 # LUK lowers the loss
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    t = feed(g, [51900 - round(NEED * 0.04)], t0=t)
    assert len(g.summary(t)["deaths"]) == 1


def test_a_bigger_drop_is_a_misread(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    t = feed(g, [51900 - round(NEED * 0.30)], t0=t)
    assert g.summary(t)["deaths"] == []


def test_one_low_read_is_not_a_death(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    g.update(50000, pct(50000), 32, 1, "Ant Tunnel I", t)          # one read only
    t = feed(g, [52000], t0=t + 2)
    assert g.summary(t)["deaths"] == []


def test_after_a_death_the_next_kill_counts_from_the_lower_bar(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    low = 51900 - round(NEED * 0.10)
    t = feed(g, [low, low + 100], t0=t)
    assert g.summary(t)["gained"] == 1900 - round(NEED * 0.10) + 100


def test_deaths_lower_exp_per_hour_and_are_saved(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])
    hr = g.summary(t)["exp_hr"]
    t = feed(g, [60000 - round(NEED * 0.10)], t0=t)
    assert g.summary(t)["exp_hr"] < hr
    g.flush(t)
    row = g.db.execute("SELECT deaths, exp_lost FROM sessions").fetchone()
    assert row == (1, round(NEED * 0.10))
