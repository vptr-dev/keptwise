"""App settings stored in the database as small JSON values.

Never store API keys here: they go to Windows Credential Manager
(see app/ai/secrets.py).
"""

from __future__ import annotations

import json
from typing import Any

from app.db.connection import Database


class SettingsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set(self, key: str, value: Any) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json",
                (key, json.dumps(value)),
            )

    def all(self) -> dict[str, Any]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}
