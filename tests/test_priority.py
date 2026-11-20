"""Companion runs below normal priority, so the game always comes first (2026-11-20: it ran at Normal,
the same as the game, using ~19% of a core)."""
import companion


def test_below_normal_is_asked_for():
    asked = []
    assert companion.lower_priority(setter=asked.append) is True
    assert asked == [0x4000]


def test_a_failure_is_not_fatal():
    def fail(cls):
        raise OSError("access denied")
    assert companion.lower_priority(setter=fail) is False
