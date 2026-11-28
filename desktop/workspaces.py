"""Workspace names and the next workspace to open. Library files stay in place."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4


class Workspaces:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.catalog = root / "workspaces.sqlite"
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS spaces (id TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, active INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO spaces VALUES ('default','Personal',1)")
            self.current = db.execute("SELECT id FROM spaces WHERE active=1").fetchone()[0]

    @property
    def directory(self):
        return self.root if self.current == "default" else self.root / "workspaces" / self.current

    def list(self):
        with closing(sqlite3.connect(self.catalog)) as db:
            return {"current": self.current, "items": [{"id": key, "name": name} for key, name in
                    db.execute("SELECT id,name FROM spaces ORDER BY rowid")]}

    def create(self, name, restored: Path | None = None):
        name = name.strip()
        if not 1 <= len(name) <= 60:
            raise ValueError("Use a name between 1 and 60 characters.")
        with closing(sqlite3.connect(self.catalog)) as db, db:
            try:
                key = uuid4().hex
                db.execute("INSERT INTO spaces VALUES (?,?,0)", (key, name))
                if restored is not None:
                    target = self.root / "workspaces" / key
                    target.parent.mkdir(exist_ok=True)
                    restored.replace(target)
            except sqlite3.IntegrityError as error:
                raise ValueError("A workspace already has that name.") from error
        return self.list()

    def choose(self, key):
        with closing(sqlite3.connect(self.catalog)) as db, db:
            if not db.execute("SELECT 1 FROM spaces WHERE id=?", (key,)).fetchone():
                raise ValueError("Unknown workspace.")
            db.execute("UPDATE spaces SET active=(id=?)", (key,))
