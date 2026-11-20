"""While you're away from the game (no EXP for 5 minutes and the game isn't the window in front),
Companion looks at it every 5 s instead of every 1.5 s, and keeps two frames a second instead of
seven. 2026-11-20: the game stayed open all night and Companion read it at full pace throughout."""
import sniper

NOW = 100000.0


def test_away_five_minutes_is_idle():
    assert sniper.is_idle(NOW - 301, NOW - 9999, NOW, in_front=False, shop_open=False) is True


def test_grinding_behind_the_dashboard_is_not_idle():
    assert sniper.is_idle(NOW - 20, NOW - 9999, NOW, in_front=False, shop_open=False) is False


def test_back_in_front_is_not_idle():
    assert sniper.is_idle(NOW - 3600, NOW - 9999, NOW, in_front=True, shop_open=False) is False


def test_an_open_shop_is_never_idle():
    assert sniper.is_idle(NOW - 3600, NOW - 9999, NOW, in_front=False, shop_open=True) is False


def test_no_gain_yet_counts_from_start():
    assert sniper.is_idle(None, NOW - 200, NOW, in_front=False, shop_open=False) is False
    assert sniper.is_idle(None, NOW - 400, NOW, in_front=False, shop_open=False) is True


# ---- review fixes: what counts as being here
from types import SimpleNamespace


def test_a_rising_hud_exp_is_activity():
    a = SimpleNamespace()
    sniper.note_exp_rise(a, 50000, 30, 1.0)
    assert getattr(a, "exp_moved_at", None) is None            # the first read: nothing to compare with
    sniper.note_exp_rise(a, 50060, 30, 2.0)
    assert a.exp_moved_at == 2.0
    sniper.note_exp_rise(a, 50060, 30, 9.0)
    assert a.exp_moved_at == 2.0
    sniper.note_exp_rise(a, 100, 31, 12.0)                       # a level-up: the bar starts over
    assert a.exp_moved_at == 12.0


def test_a_flickering_last_digit_isnt_activity():
    a = SimpleNamespace()
    for t, e in enumerate([52900, 52908, 52900, 52908, 52900, 52908]):
        sniper.note_exp_rise(a, e, 30, float(t))
    assert a.exp_moved_at == 1.0


def fake(**kw):
    base = dict(game_hwnd=5, user_hidden=False, shop_anchor=None, myshop_anchor=None, started_at=NOW - 9999,
                active_at=None, exp_moved_at=None)
    return SimpleNamespace(**{**base, **kw})


def test_a_map_change_doesnt_make_you_away(monkeypatch):
    # Grind starts a new session on a map change; being here is the app's own clock, not the session's
    monkeypatch.setattr(sniper, "foreground_window", lambda: 9)
    monkeypatch.setattr(sniper.time, "time", lambda: NOW)
    assert sniper.App.idle(fake(exp_moved_at=NOW - 10)) is False


def test_hidden_labels_with_the_game_in_front_isnt_away(monkeypatch):
    monkeypatch.setattr(sniper, "foreground_window", lambda: 5)
    monkeypatch.setattr(sniper.time, "time", lambda: NOW)
    assert sniper.App.idle(fake(user_hidden=True)) is False


def test_the_game_in_front_a_while_ago_counts(monkeypatch):
    monkeypatch.setattr(sniper, "foreground_window", lambda: 9)
    monkeypatch.setattr(sniper.time, "time", lambda: NOW)
    assert sniper.App.idle(fake(active_at=NOW - 60)) is False
    assert sniper.App.idle(fake(active_at=NOW - 400)) is True
