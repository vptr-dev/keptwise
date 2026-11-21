"""Undo and redo for everything the user changes.

How it works: while a request from the app changes something, temporary
triggers on that one database connection write down the SQL that would put
each changed row back (SQLite's classic undo log). All of that request's
lines form one step with a plain label ("Delete collection"). Undo runs a
step's lines backwards, while the same triggers write down how to redo it.

Only the user's own data is recorded (saves, collections, tags, plans,
spaces...). Background jobs use their own connections without the triggers,
so a transcript finishing in the background is never "undone" by accident.
Settings, chats and the search index aren't recorded either.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from contextvars import ContextVar
from typing import Any

# The step the current request is recording into (None: not recording).
recording: ContextVar[int | None] = ContextVar("undo_recording", default=None)

RECORDED = (
    "items", "transcripts", "ai_results", "collections", "item_collections", "spaces", "tags", "item_tags",
    "plans", "plan_items", "plan_tasks", "platform_links", "platform_import_destinations", "removed_links",
)
STEPS_KEPT = 100
# Sent by the AI with each action, so one answer's actions undo together.
UNDO_STEP_HEADER = "x-keptwise-undo-step"
REPLAY_STEP = -1  # undo/redo write their own opposite here first

LABELS: list[tuple[str, str, str]] = [
    ("POST", r"/api/collections$", "New collection"),
    ("POST", r"/api/collections/bulk$", "Change collections"),
    ("POST", r"/api/collections/\d+/merge$", "Merge collections"),
    ("POST", r"/api/collections/\d+/place$", "Move collection"),
    ("POST", r"/api/collections/\d+/icon$", "Change collection picture"),
    ("PATCH", r"/api/collections/\d+$", "Change collection"),
    ("DELETE", r"/api/collections/\d+$", "Delete collection"),
    ("POST", r"/api/spaces$", "New space"),
    ("PATCH", r"/api/spaces/\d+$", "Change space"),
    ("DELETE", r"/api/spaces/\d+$", "Delete space"),
    ("POST", r"/api/tags$", "New tag"),
    ("PATCH", r"/api/tags/\d+$", "Change tag"),
    ("DELETE", r"/api/tags/\d+$", "Delete tag"),
    ("POST", r"/api/tags/merge$", "Merge tags"),
    ("POST", r"/api/tags/delete$", "Delete tags"),
    ("POST", r"/api/items/\d+/tags$", "Tag a save"),
    ("DELETE", r"/api/items/\d+/tags/\d+$", "Take a tag off"),
    ("POST", r"/api/unsave/clear$", "Clear the Unsave checklist"),
    ("POST", r"/api/items/bulk$", "Change saves"),
    ("PATCH", r"/api/items/\d+$", "Change a save"),
    ("DELETE", r"/api/items/\d+$", "Delete a save for good"),
    ("POST", r"/api/items/\d+/move$", "Move a save"),
    ("DELETE", r"/api/items/\d+/collections/\d+$", "Take a save out of a collection"),
    ("PUT", r"/api/items/\d+/steps/\d+$", "Tick a step"),
    ("POST", r"/api/review/\d+/accept$", "Put a save in a collection"),
    ("POST", r"/api/review/accept-all$", "Accept all suggestions"),
    ("POST", r"/api/items/\d+/tag-suggestions$", "Suggested tags"),
    ("POST", r"/api/sorting/clear$", "Clear the AI's work"),
    ("POST", r"/api/plans$", "New plan"),
    ("POST", r"/api/plans/\d+/copy$", "Copy plan"),
    ("PATCH", r"/api/plans/\d+$", "Change plan"),
    ("DELETE", r"/api/plans/\d+$", "Delete plan"),
    ("POST", r"/api/plans/\d+/items$", "Add to plan"),
    ("DELETE", r"/api/plans/\d+/items/\d+$", "Take out of plan"),
    ("POST", r"/api/plans/\d+/tasks$", "Add a to-do"),
    ("DELETE", r"/api/plans/\d+/tasks/\d+$", "Delete a to-do"),
    ("", r"/api/plans/", "Change plan"),
    ("PUT", r"/api/platform-collections/default$", "Change import destination"),
    ("", r"/api/platform-collections", "Change platform collections"),
]

# Requests that are never a step of their own.
NOT_RECORDED = re.compile(r"^/api/(undo|redo|jobs|updates|session|storage|dev|imports|sorting/settings$|ai/|assistant/)")


def label_for(method: str, path: str) -> str:
    for wanted, pattern, label in LABELS:
        if (not wanted or wanted == method) and re.search(pattern, path):
            return label
    return "Change"


def should_record(method: str, path: str) -> bool:
    return method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/") and not NOT_RECORDED.match(path)


def _rowid_alias(columns: list[sqlite3.Row | tuple[Any, ...]]) -> str | None:
    keys = [c for c in columns if c[5]]
    if len(keys) == 1 and str(keys[0][2]).upper() == "INTEGER":
        return str(keys[0][1])
    return None


def trigger_sql(conn: sqlite3.Connection) -> str:
    """CREATE TEMP TRIGGER statements for every recorded table."""
    parts = []
    for table in RECORDED:
        columns = list(conn.execute(f"PRAGMA main.table_info({table})"))
        if not columns:
            continue
        names = [str(c[1]) for c in columns]
        alias = _rowid_alias(columns)
        insert_cols = names if alias else ["rowid", *names]
        values = " || ',' || ".join(f"quote(OLD.\"{n}\")" for n in insert_cols)
        log = "INSERT INTO main.undo_log (step, sql) SELECT step, {sql} FROM temp.undo_now"
        put_back = f"'INSERT INTO \"{table}\" ({', '.join(chr(34) + n + chr(34) for n in insert_cols)}) VALUES (' || {values} || ')'"
        take_out = f"'DELETE FROM \"{table}\" WHERE rowid = ' || NEW.rowid"
        changes = " || ".join(
            f"(CASE WHEN OLD.\"{n}\" IS NOT NEW.\"{n}\" THEN ',\"{n}\" = ' || quote(OLD.\"{n}\") ELSE '' END)"
            for n in names
        )
        changed = " OR ".join(f"OLD.\"{n}\" IS NOT NEW.\"{n}\"" for n in names)
        change_back = f"'UPDATE \"{table}\" SET ' || substr({changes}, 2) || ' WHERE rowid = ' || OLD.rowid"
        parts.append(
            f"CREATE TEMP TRIGGER undo_{table}_i AFTER INSERT ON main.\"{table}\" BEGIN "
            f"{log.format(sql=take_out)}; END;\n"
            f"CREATE TEMP TRIGGER undo_{table}_d AFTER DELETE ON main.\"{table}\" BEGIN "
            f"{log.format(sql=put_back)}; END;\n"
            f"CREATE TEMP TRIGGER undo_{table}_u AFTER UPDATE ON main.\"{table}\" WHEN {changed} BEGIN "
            f"{log.format(sql=change_back)}; END;\n"
        )
    return "".join(parts)


class UndoHistory:
    def __init__(self, db: Any) -> None:
        self.db = db
        self._lock = threading.Lock()
        self._triggers: str | None = None
        with db.connect() as conn:
            if db.backup_made is not None:
                self._forget(conn)  # the layout changed: old steps may not fit any more
            row = conn.execute("SELECT max(id) FROM undo_steps").fetchone()
            self._next = int(row[0] or 0) + 1
        db.undo = self

    # ---------- recording ----------

    def start_recording(self, conn: sqlite3.Connection, step: int) -> None:
        """Called by Database.connect() while a request is recording."""
        if self._triggers is None:
            self._triggers = trigger_sql(conn)
        conn.execute("PRAGMA recursive_triggers=ON")  # so REPLACE deletes are written down too
        conn.executescript(
            "CREATE TEMP TABLE IF NOT EXISTS undo_now (step INTEGER);" + self._triggers
        )
        conn.execute("DELETE FROM temp.undo_now")
        conn.execute("INSERT INTO temp.undo_now VALUES (?)", (step,))

    def new_step(self) -> int:
        with self._lock:
            step = self._next
            self._next += 1
            return step

    def finish(self, step: int, label: str) -> bool:
        """Keep the step if it changed anything. A new step clears what could be redone."""
        token = recording.set(None)
        try:
            with self._lock, self.db.connect() as conn:
                if conn.execute("SELECT 1 FROM undo_log WHERE step = ? LIMIT 1", (step,)).fetchone() is None:
                    return False
                undone = [r[0] for r in conn.execute("SELECT id FROM undo_steps WHERE state = 'undone'")]
                for old in undone:
                    conn.execute("DELETE FROM undo_log WHERE step = ?", (old,))
                conn.execute("DELETE FROM undo_steps WHERE state = 'undone'")
                conn.execute(
                    "INSERT INTO undo_steps (id, label, state) VALUES (?, ?, 'done') "
                    "ON CONFLICT(id) DO UPDATE SET label = excluded.label",
                    (step, label),
                )
                extra = [r[0] for r in conn.execute(
                    "SELECT id FROM undo_steps ORDER BY id DESC LIMIT -1 OFFSET ?", (STEPS_KEPT,)
                )]
                for old in extra:
                    conn.execute("DELETE FROM undo_log WHERE step = ?", (old,))
                    conn.execute("DELETE FROM undo_steps WHERE id = ?", (old,))
                return True
        finally:
            recording.reset(token)

    # ---------- undo and redo ----------

    def state(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            done = conn.execute("SELECT id, label FROM undo_steps WHERE state = 'done' ORDER BY id DESC LIMIT 1").fetchone()
            undone = conn.execute("SELECT id, label FROM undo_steps WHERE state = 'undone' ORDER BY id LIMIT 1").fetchone()
        return {
            "undo": {"id": done[0], "label": done[1]} if done else None,
            "redo": {"id": undone[0], "label": undone[1]} if undone else None,
        }

    def undo(self, expected_id: int | None = None) -> str:
        return self._replay("done", "undone", "DESC", expected_id)

    def redo(self) -> str:
        return self._replay("undone", "done", "ASC")

    def _replay(self, have: str, becomes: str, order: str, expected_id: int | None = None) -> str:
        token = recording.set(None)
        try:
            with self._lock, self.db.connect() as conn:
                row = conn.execute(
                    f"SELECT id, label FROM undo_steps WHERE state = ? ORDER BY id {order} LIMIT 1", (have,)
                ).fetchone()
                if row is None:
                    raise LookupError("There's nothing to undo." if have == "done" else "There's nothing to redo.")
                step, label = int(row[0]), str(row[1])
                if expected_id is not None and step != expected_id:
                    raise LookupError("A newer change comes first. Use the main Undo button to take it back.")
                lines = [r[0] for r in conn.execute("SELECT sql FROM undo_log WHERE step = ? ORDER BY id DESC", (step,))]
                self.start_recording(conn, REPLAY_STEP)
                conn.execute("PRAGMA defer_foreign_keys=ON")  # rows come back parents and children in any order
                try:
                    for line in lines:
                        conn.execute(line)
                except sqlite3.Error as error:
                    conn.rollback()
                    self._drop(conn, step)
                    conn.commit()
                    raise RuntimeError(
                        f"\"{label}\" can't be {'undone' if have == 'done' else 'redone'} any more: "
                        "something it touched has changed since."
                    ) from error
                conn.execute("DELETE FROM temp.undo_now")
                conn.execute("DELETE FROM undo_log WHERE step = ?", (step,))
                conn.execute("UPDATE undo_log SET step = ? WHERE step = ?", (step, REPLAY_STEP))
                conn.execute("UPDATE undo_steps SET state = ? WHERE id = ?", (becomes, step))
                return label
        finally:
            recording.reset(token)

    def _drop(self, conn: sqlite3.Connection, step: int) -> None:
        conn.execute("DELETE FROM undo_log WHERE step = ?", (step,))
        conn.execute("DELETE FROM undo_steps WHERE id = ?", (step,))

    def _forget(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM undo_log")
        conn.execute("DELETE FROM undo_steps")
