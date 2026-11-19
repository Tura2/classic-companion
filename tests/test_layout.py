"""The repo root holds the entry point only; the app's modules live in app/ (2026-11-19)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_only_the_entry_point_is_a_module_in_the_root():
    assert sorted(p.name for p in ROOT.glob("*.py")) == ["companion.py"]


def test_paths_still_find_the_repo_folders():
    import paths
    assert paths.APP_DIR == ROOT and paths.RES_DIR == ROOT
    assert (paths.RES_DIR / "web").is_dir() and (paths.RES_DIR / "assets").is_dir()
