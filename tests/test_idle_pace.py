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
