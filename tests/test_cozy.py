"""Cozy Market prices refresh at a pace a pass can keep. 2026-11-20: prices were fetched again once
over 2 hours old, but a pass at a page a second took ~4.7 h, so a new pass began 10 minutes after each
ended, all day; the 149 pages that fail were tried again on every pass."""
from datetime import datetime, timedelta, timezone

import cozy


def ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_fresh_failure_waits_for_the_next_pass():
    assert cozy.wanted({"error": "HTTP 404", "fetched": cozy.now()}, 12) is False


def test_an_old_failure_without_a_time_is_fetched():
    assert cozy.wanted({"error": "HTTP 404"}, 12) is True


def test_a_failure_older_than_the_pace_is_fetched():
    assert cozy.wanted({"error": "HTTP 404", "fetched": ago(13)}, 12) is True


def test_full_runs_still_retry_failures():
    assert cozy.wanted({"error": "x", "fetched": cozy.now()}, None) is True


def test_a_priced_row_waits_until_it_is_old():
    row = {"name": "Iron Ore", "price": 299, "fetched": ago(1)}
    assert cozy.wanted(row, 12) is False and cozy.wanted({**row, "fetched": ago(13)}, 12) is True


def test_a_pass_fits_the_pace():
    # measured live: 1,459 pages in 281 min, ~11.6 s a page with the failing pages' timeouts; a pass
    # over all ~2,200 items must end before the next is due
    assert cozy.EVERY_HOURS * 3600 >= 2200 * 281 * 60 / 1459


def test_a_priced_page_that_failed_waits_too():
    row = {"name": "Iron Ore", "price": 299, "fetched": ago(13), "tried": cozy.now()}
    assert cozy.wanted(row, 12) is False


def test_a_failed_refetch_keeps_the_price_and_notes_the_try(tmp_path, monkeypatch):
    import json
    path, fetched = tmp_path / "cozy.json", ago(13)
    path.write_text(json.dumps({"items": {"7": {"name": "Iron Ore", "price": 299, "fetched": fetched}}}), "utf-8")
    monkeypatch.setattr(cozy, "item_ids", lambda: [7])
    monkeypatch.setattr(cozy, "get", lambda url: (_ for _ in ()).throw(TimeoutError("timed out")))
    monkeypatch.setattr(cozy.time, "sleep", lambda s: None)
    cozy.refresh(path, older_than=12, workers=1, delay=0, say=lambda *a: None)
    row = json.loads(path.read_text("utf-8"))["items"]["7"]
    assert row["price"] == 299 and row["fetched"] == fetched       # the price keeps its own age
    assert cozy.wanted(row, 12) is False                                                 # and it waits a pass
