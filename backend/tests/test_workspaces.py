from pathlib import Path

import pytest

from app.ai.secrets import KeyringStore
from app.db.connection import Database
from app.db.items_repo import NewItem, upsert_item
from app.db.settings_repo import SettingsRepo
from app.paths import AppPaths


def test_switch_and_return_preserve_original_library_and_settings(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "desktop"))
    from workspaces import Workspaces

    spaces = Workspaces(tmp_path)
    original = Database(AppPaths(spaces.directory).create().database)
    SettingsRepo(original).set("test.preference", "blue")
    with original.connect() as conn:
        upsert_item(conn, NewItem("tiktok", "https://example.com/personal"))
    key = spaces.create("Study")["items"][-1]["id"]
    with pytest.raises(ValueError):
        spaces.create(" study ")
    with pytest.raises(ValueError):
        spaces.choose("../")
    spaces.choose(key)
    study = Workspaces(tmp_path)
    db = Database(AppPaths(study.directory).create().database)
    assert SettingsRepo(db).get("test.preference", None) is None
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    SettingsRepo(db).set("test.preference", "red")
    assert KeyringStore(key).service != KeyringStore().service
    study.choose("default")
    restored = Database(AppPaths(Workspaces(tmp_path).directory).database)
    assert SettingsRepo(restored).get("test.preference", None) == "blue"
    with restored.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_library_backup_restores_a_separate_workspace(tmp_path, monkeypatch):
    from app.library.backup import unpack_backup, write_backup

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "desktop"))
    from workspaces import Workspaces

    root = tmp_path / "profile"
    spaces = Workspaces(root)
    paths = AppPaths(spaces.directory).create()
    original = Database(paths.database)
    with original.connect() as conn:
        upsert_item(conn, NewItem("youtube", "https://example.com/watch"))
    (paths.thumbnails / "image.jpg").write_bytes(b"picture")
    archive = tmp_path / "saved.zip"
    write_backup(paths, archive)
    staging = tmp_path / "preview"
    staging.mkdir()
    assert unpack_backup(archive, staging) == {"saves": 1, "collections": 0}
    key = spaces.create("Restored", restored=staging)["items"][-1]["id"]
    assert spaces.current == "default"
    spaces.choose(key)
    restored = AppPaths(Workspaces(root).directory)
    assert restored.database != paths.database
    assert (restored.thumbnails / "image.jpg").read_bytes() == b"picture"
    with Database(restored.database).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
