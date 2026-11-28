"""Portable snapshots of one workspace, restored into a separate workspace."""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path, PureWindowsPath
from zipfile import ZIP_DEFLATED, ZipFile

from app.db.migrations import MIGRATIONS
from app.paths import AppPaths

MEDIA = ("thumbnails", "collection-icons")
FILE = re.compile(r"(?:thumbnails|collection-icons)/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*")
DATABASE = "saves.db"


def write_backup(paths: AppPaths, destination: Path) -> None:
    """Take a consistent SQLite snapshot and include its accompanying pictures."""
    if destination.suffix.lower() != ".zip":
        raise ValueError("Choose a .zip file for the backup.")
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        folder = Path(temp)
        database = folder / DATABASE
        with closing(sqlite3.connect(paths.database)) as source, closing(sqlite3.connect(database)) as copy:
            source.backup(copy)
        archive = folder / "backup.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            bundle.write(database, DATABASE)
            for name in MEDIA:
                for path in (paths.root / name).iterdir():
                    entry = f"{name}/{path.name}"
                    if path.is_file() and not path.is_symlink() and FILE.fullmatch(entry):
                        bundle.write(path, entry)
        archive.replace(destination)


def _schema(db: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return db.execute(
        "SELECT type, name, sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()


def unpack_backup(archive: Path, target: Path) -> dict[str, int]:
    """Extract supported paths only and check the database before offering Restore."""
    with ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = {entry.filename.lower() for entry in entries}
        if DATABASE not in names or len(entries) != len(names) or len(entries) > 100_000:
            raise ValueError("This archive isn't a Keptwise workspace backup.")
        if sum(entry.file_size for entry in entries) + 64 * 1024**2 > shutil.disk_usage(target).free:
            raise ValueError("There isn't enough disk space to restore this backup.")
        for entry in entries:
            name = entry.filename
            if name != DATABASE and (not FILE.fullmatch(name) or name.endswith(".") or PureWindowsPath(name).is_reserved()):
                raise ValueError("The backup contains an unexpected file.")
            path = target / name
            path.parent.mkdir(exist_ok=True)
            with bundle.open(entry) as source, path.open("xb") as dest:
                shutil.copyfileobj(source, dest)

    database = (target / DATABASE).resolve().as_uri()
    with closing(sqlite3.connect(database + "?mode=rw", uri=True)) as db, db:
        db.execute("PRAGMA trusted_schema=OFF")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if not 1 <= version <= len(MIGRATIONS):
            raise ValueError("This backup uses a different Keptwise database version.")
        with closing(sqlite3.connect(":memory:")) as reference:
            for script in MIGRATIONS[:version]:
                reference.executescript(script)
            if _schema(db) != _schema(reference):
                raise ValueError("The backup's database structure does not match Keptwise.")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("The backup's database did not pass its integrity check.")
        # Undo entries contain SQL from the original workspace. A restored
        # workspace starts a fresh undo history.
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='undo_log'").fetchone():
            db.execute("DELETE FROM undo_log")
            db.execute("DELETE FROM undo_steps")
        return {
            "saves": db.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "collections": db.execute("SELECT COUNT(*) FROM collections").fetchone()[0],
        }
