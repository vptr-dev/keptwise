"""Opening the SQLite database.

Each piece of work opens its own short-lived connection with
`with db.connect() as conn:`. SQLite connections are cheap, and this way
background jobs and web requests never share one across threads.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.db.migrations import MIGRATIONS, migrate, schema_version
from app.db.undo import recording

BACKUPS_KEPT = 5


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.undo: Any = None  # app.db.undo.UndoHistory, once the app sets it up
        path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_made: Path | None = self._backup_before_update()
        with self.connect() as conn:
            # WAL lets readers keep reading while a job writes.
            conn.execute("PRAGMA journal_mode=WAL")
            migrate(conn)

    def _backup_before_update(self) -> Path | None:
        """Before a newer version of the app changes the database's layout,
        keep a copy next to it (backups\\saves-v<N>-<time>.db). The newest
        few are kept. Returns the copy's path, or None when none was needed."""
        if not self.path.exists():
            return None
        source = sqlite3.connect(self.path, timeout=10)
        try:
            version = schema_version(source)
            if version == 0 or version >= len(MIGRATIONS):
                return None
            folder = self.path.parent / "backups"
            folder.mkdir(exist_ok=True)
            target = folder / f"{self.path.stem}-v{version}-{time.strftime('%Y%m%d-%H%M%S')}.db"
            copy = sqlite3.connect(target)
            try:
                source.backup(copy)  # a consistent copy, even with a WAL file
            finally:
                copy.close()
        finally:
            source.close()
        old = sorted(folder.glob(f"{self.path.stem}-v*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
        for extra in old[BACKUPS_KEPT:]:
            extra.unlink(missing_ok=True)
        return target

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection; commit if the block succeeds, roll back if not."""
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row  # rows work like dicts: row["title"]
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        step = recording.get()
        if step is not None and self.undo is not None:
            self.undo.start_recording(conn, step)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def size_bytes(self) -> int:
        """Size of the database files on disk (main file plus WAL)."""
        total = 0
        for suffix in ("", "-wal"):
            file = Path(str(self.path) + suffix)
            if file.exists():
                total += file.stat().st_size
        return total
