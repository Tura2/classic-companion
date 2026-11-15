"""Companion keeps everything in one folder: your data in data\\, the rest in their own subfolders."""
import paths


def test_the_folders_sit_under_the_app_folder():
    for d in (paths.DATA_DIR, paths.CACHE_DIR, paths.LOGS_DIR, paths.DEBUG_DIR, paths.REPORTS_DIR):
        assert d.parent == paths.APP_DIR
    assert [d.name for d in (paths.DATA_DIR, paths.LOGS_DIR, paths.REPORTS_DIR)] == ["data", "logs", "reports"]


def test_loose_data_files_move_into_data(tmp_path):
    (tmp_path / "profile.json").write_text('{"level": 33}')
    (tmp_path / "scans.sqlite").write_bytes(b"db")
    (tmp_path / "builds.json").write_text("{}")            # not data: stays where it is
    moved = paths.migrate(tmp_path)
    assert sorted(moved) == ["profile.json", "scans.sqlite"]
    assert (tmp_path / "data" / "profile.json").read_text() == '{"level": 33}'
    assert not (tmp_path / "profile.json").exists()
    assert (tmp_path / "builds.json").exists()


def test_a_file_already_in_data_wins(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.json").write_text("new")
    (tmp_path / "config.json").write_text("old")
    assert paths.migrate(tmp_path) == []
    assert (tmp_path / "data" / "config.json").read_text() == "new"
    assert (tmp_path / "config.json").read_text() == "old"     # left alone, never lost


def test_nothing_loose_is_a_no_op(tmp_path):
    assert paths.migrate(tmp_path) == []
    assert (tmp_path / "data").is_dir()
