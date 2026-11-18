"""Ticking steps, marking an item done, and marking it unsaved.

Steps live in ai_results.steps_json as [{"text": ..., "done": false}, ...],
so a tick is stored right next to the step it belongs to.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.items_repo import update_item


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _steps(conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]] | None:
    row = conn.execute("SELECT steps_json FROM ai_results WHERE item_id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    try:
        raw = json.loads(row["steps_json"] or "[]")
    except ValueError:
        raw = []
    # Older or odd answers may hold plain strings: turn them into the dict shape.
    return [step if isinstance(step, dict) else {"text": str(step), "done": False} for step in raw]


def tick_step(conn: sqlite3.Connection, item_id: int, index: int, done: bool) -> None:
    """Tick (or untick) one step. The first tick marks the item as started."""
    steps = _steps(conn, item_id)
    if steps is None or not 0 <= index < len(steps):
        raise IndexError("No such step.")
    steps[index]["done"] = done
    conn.execute(
        "UPDATE ai_results SET steps_json = ?, updated_at = ? WHERE item_id = ?",
        (json.dumps(steps), now_iso(), item_id),
    )
    if done:
        started = conn.execute("SELECT started_at FROM items WHERE id = ?", (item_id,)).fetchone()
        if started and not started["started_at"]:
            update_item(conn, item_id, started_at=now_iso())


def set_done(conn: sqlite3.Connection, item_id: int, done: bool) -> None:
    """Mark the whole item done (or not)."""
    fields: dict[str, Any] = {"done": int(done), "done_at": now_iso() if done else None}
    if done:
        row = conn.execute("SELECT started_at FROM items WHERE id = ?", (item_id,)).fetchone()
        if row and not row["started_at"]:
            fields["started_at"] = now_iso()
    update_item(conn, item_id, **fields)


def set_safe(conn: sqlite3.Connection, item_id: int, safe: bool) -> None:
    """The user says this one is (or isn't) safe to unsave, whatever the rule."""
    update_item(conn, item_id, safe_to_unsave=int(safe))


def set_unsaved(conn: sqlite3.Connection, item_id: int, unsaved: bool) -> None:
    """The user has unsaved it on the platform themselves (the app never does)."""
    update_item(conn, item_id, unsaved=int(unsaved), unsaved_at=now_iso() if unsaved else None)


def set_deleted(conn: sqlite3.Connection, item_id: int, deleted: bool) -> None:
    """Delete a save (it moves to the Archive and leaves every list) or put
    it back. Nothing about it is lost: notes, tags, collections and plans
    are all still there when it comes back. A deleted save goes on the
    Unsave list: you don't want it, so it can go from the platform too."""
    if deleted:
        update_item(conn, item_id, deleted_at=now_iso(), safe_to_unsave=1)
    else:
        update_item(conn, item_id, deleted_at=None)


def purge(conn: sqlite3.Connection, item_id: int) -> list[str]:
    """Delete a save for good, with its transcript, notes and tags. Its link
    is remembered so an import never brings it back. Returns the names of
    its files (picture, leftover sound) for the caller to remove."""
    row = conn.execute("SELECT platform, url, thumbnail_path FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return []
    conn.execute("INSERT OR IGNORE INTO removed_links (platform, url) VALUES (?, ?)", (row["platform"], row["url"]))
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return [str(row["thumbnail_path"])] if row["thumbnail_path"] else []


def restart(conn: sqlite3.Connection, item_id: int) -> None:
    """Untick every step and take the item off the Plans list."""
    steps = _steps(conn, item_id)
    if steps is not None:
        for step in steps:
            step["done"] = False
        conn.execute("UPDATE ai_results SET steps_json = ? WHERE item_id = ?", (json.dumps(steps), item_id))
    update_item(conn, item_id, started_at=None, done=0, done_at=None)
