"""Tests for the database: migrations, items, settings and stats."""

from __future__ import annotations

from pathlib import Path

from app.db.connection import Database
from app.db.items_repo import (
    NewItem,
    get_item_row,
    get_transcript,
    item_ids_with_status,
    save_transcript,
    update_item,
    upsert_item,
)
from app.db.migrations import MIGRATIONS, schema_version
from app.db.settings_repo import SettingsRepo
from app.db.stats import database_stats
from app.paths import AppPaths


def test_migrations_run_once_and_set_version(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    with db.connect() as conn:
        assert schema_version(conn) == len(MIGRATIONS)
    # Opening again must not try to create the tables a second time.
    db_again = Database(tmp_path / "a.db")
    with db_again.connect() as conn:
        assert schema_version(conn) == len(MIGRATIONS)


def test_upsert_is_duplicate_safe(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    item = NewItem(platform="tiktok", url="https://www.tiktok.com/@a/video/1")
    with db.connect() as conn:
        first_id, created = upsert_item(conn, item)
        assert created
        # Same URL again, now with an author: no new row, blank filled in.
        item.author = "chef_anna"
        second_id, created_again = upsert_item(conn, item)
        assert second_id == first_id and not created_again
        row = get_item_row(conn, first_id)
    assert row is not None
    assert row["author"] == "chef_anna"
    assert row["status"] == "imported"


def test_update_item_and_status_lookup(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    with db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("youtube", "https://youtu.be/x"))
        update_item(conn, item_id, status="enriched", title="How to bake")
        assert item_ids_with_status(conn, "enriched") == [item_id]
        assert item_ids_with_status(conn, "imported") == []


def test_update_item_refuses_unknown_fields(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    with db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("youtube", "https://youtu.be/x"))
        try:
            update_item(conn, item_id, id=99)
        except ValueError as error:
            assert "id" in str(error)
        else:
            raise AssertionError("update_item accepted an unknown field")


def test_transcripts_are_saved_and_replaced(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    with db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("youtube", "https://youtu.be/x"))
        save_transcript(conn, item_id, "first", "en", "test")
        save_transcript(conn, item_id, "second", "en", "test")
        transcript = get_transcript(conn, item_id)
    assert transcript == {"text": "second", "language": "en", "source": "test"}


def test_settings_round_trip(tmp_path: Path) -> None:
    settings = SettingsRepo(Database(tmp_path / "a.db"))
    assert settings.get("theme", "system") == "system"
    settings.set("theme", "dark")
    settings.set("limits", {"batch": 50})
    assert settings.get("theme") == "dark"
    assert settings.all() == {"theme": "dark", "limits": {"batch": 50}}


def test_stats_counts_tables(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")
    with db.connect() as conn:
        upsert_item(conn, NewItem("tiktok", "https://t/1"))
        upsert_item(conn, NewItem("tiktok", "https://t/2"))
    stats = database_stats(db)
    assert stats["tables"]["items"] == 2
    assert stats["items_by_status"] == {"imported": 2}
    assert stats["schema_version"] == len(MIGRATIONS)
    assert stats["size_bytes"] > 0


def test_app_paths_creates_all_folders(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "Keptwise").create()
    for folder in (paths.thumbnails, paths.audio, paths.models, paths.imports, paths.logs):
        assert folder.is_dir()
    assert paths.database.parent == paths.root
