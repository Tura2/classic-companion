"""Go to remembers the last places you navigated to, newest first, each once."""
import companion


def test_recent_destinations_newest_first_no_repeats():
    prof = {}
    for m in (1, 2, 3, 2, 4, 5, 6):
        companion.remember_recent(prof, m)
    assert prof["recent_nav"] == [6, 5, 4, 2, 3]
