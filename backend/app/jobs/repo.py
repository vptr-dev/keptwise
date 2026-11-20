"""Job records in the database, so progress survives an app restart."""

from __future__ import annotations

import json
from typing import Any

from app.db.connection import Database

# Jobs in these states are finished and will not change again.
FINISHED = ("done", "failed", "cancelled")

_UPDATABLE = {"status", "progress", "total", "message", "error", "result_json", "finished_at", "notice_dismissed"}


def _to_dict(row: Any) -> dict[str, Any]:
    job = dict(row)
    job["notice_dismissed"] = bool(job["notice_dismissed"])
    job["params"] = json.loads(job.pop("params_json") or "{}")
    result = job.pop("result_json")
    job["result"] = json.loads(result) if result else None
    return job


class JobsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, kind: str, title: str, params: dict[str, Any]) -> int:
        with self._db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (kind, title, status, params_json) VALUES (?, ?, 'queued', ?)",
                (kind, title, json.dumps(params)),
            )
            return int(cursor.lastrowid or 0)

    def get(self, job_id: int) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _to_dict(row) if row else None

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_to_dict(row) for row in rows]

    def dismiss_notice(self, job_id: int) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute(
                """UPDATE jobs SET notice_dismissed = 1
                   WHERE id = ? AND status IN ('done', 'failed', 'cancelled', 'interrupted')""",
                (job_id,),
            )
            return cursor.rowcount > 0

    def active_title(self) -> str | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT title FROM jobs WHERE status IN ('queued', 'running', 'paused') ORDER BY id LIMIT 1"
            ).fetchone()
        return str(row["title"]) if row else None

    def update(self, job_id: int, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"Can't update these job fields: {sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._db.connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments}, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                (*fields.values(), job_id),
            )

    def mark_interrupted(self) -> list[int]:
        """After a restart, jobs that were mid-way can't still be running."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status IN ('queued', 'running', 'paused')"
            ).fetchall()
            conn.execute(
                "UPDATE jobs SET status = 'interrupted', "
                "message = 'Stopped when the app closed. Press Resume to continue.' "
                "WHERE status IN ('queued', 'running', 'paused')"
            )
        return [int(row["id"]) for row in rows]
