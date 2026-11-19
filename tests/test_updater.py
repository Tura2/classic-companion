"""Companion updates itself from the latest GitHub release, safely."""
import hashlib

import pytest

import updater


def test_versions_compare_as_numbers():
    assert updater.newer("v1.4.1", "1.4.0")
    assert updater.newer("v1.10.0", "1.9.9")
    assert not updater.newer("v1.4.0", "1.4.0")
    assert not updater.newer("v1.3.9", "1.4.0")
    assert not updater.newer("nightly", "1.4.0")          # not a version: never an update


def release(tag="v1.4.1", assets=None):
    if assets is None:
        assets = [{"name": "CompanionSetup.exe", "size": 3, "digest": "sha256:" + hashlib.sha256(b"abc").hexdigest(),
                   "browser_download_url": "https://example/CompanionSetup.exe"}]
    return {"tag_name": tag, "draft": False, "prerelease": False, "assets": assets}


def test_a_newer_release_with_the_setup_is_an_update():
    u = updater.find(lambda: release(), "1.4.0")
    assert (u.version, u.url, u.size) == ("1.4.1", "https://example/CompanionSetup.exe", 3)


@pytest.mark.parametrize("rel", [release(tag="v1.4.0"), release(assets=[]), None])
def test_no_update_when_not_newer_or_no_setup_or_no_answer(rel):
    assert updater.find(lambda: rel, "1.4.0") is None


def test_no_internet_is_no_update():
    def offline():
        raise OSError("no route")
    assert updater.find(offline, "1.4.0") is None


def test_the_download_is_kept_only_when_size_and_hash_match(tmp_path):
    u = updater.find(lambda: release(), "1.4.0")
    path = updater.download(u, tmp_path, fetch=lambda url: b"abc")
    assert path.read_bytes() == b"abc" and path.name == "CompanionSetup-1.4.1.exe"
    with pytest.raises(ValueError):
        updater.download(u, tmp_path, fetch=lambda url: b"abd")      # same size, wrong hash
    with pytest.raises(ValueError):
        updater.download(u, tmp_path, fetch=lambda url: b"ab")       # cut short
    assert sorted(p.name for p in tmp_path.iterdir()) == ["CompanionSetup-1.4.1.exe"]


def test_old_setups_are_cleaned_up(tmp_path):
    for v in ("1.3.9", "1.4.0", "1.4.1"):
        (tmp_path / f"CompanionSetup-{v}.exe").write_bytes(b"x")
    updater.clean(tmp_path, "1.4.0")
    assert [p.name for p in tmp_path.iterdir()] == ["CompanionSetup-1.4.1.exe"]


def test_the_setup_runs_hidden(monkeypatch, tmp_path):
    # the player saw Companion, then the installer's window, then Companion again: the update's
    # setup now runs with no window of its own (2026-11-19)
    seen = {}
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: seen.setdefault("args", args))
    updater.run_setup(tmp_path / "CompanionSetup-9.9.9.exe")
    assert "/VERYSILENT" in seen["args"] and "/SILENT" not in seen["args"]
    assert "/UPDATE" in seen["args"] and "/SUPPRESSMSGBOXES" in seen["args"]



def test_the_restart_after_an_update_says_so():
    # the setup starts Companion with --updated after installing (installer/companion.iss)
    assert updater.updated_note(["Companion.exe", "--updated"], "1.4.5") == "Updated to 1.4.5."
    assert updater.updated_note(["Companion.exe"], "1.4.5") is None


def test_the_installer_restarts_companion_with_updated():
    from pathlib import Path
    iss = (Path(__file__).resolve().parent.parent / "installer" / "companion.iss").read_text("utf-8")
    assert 'Parameters: "--updated"; Flags: nowait; Check: IsUpdate' in iss
