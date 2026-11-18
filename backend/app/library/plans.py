"""Plans: the user's own lists of saves to do, like "Weekend in Lisbon" or
"Meal prep this week". A plan holds one save or many, in order. Each save is
ticked off on its own, and its steps (from the AI notes) keep their own
ticks, so a plan shows both "3 of 5 videos done" and the steps inside.

A plan can also have: a day it's for (due_on), a pin that keeps it at the
top, sections ("Day 1", "To buy") that its saves and to-dos sit in, a note
on each save, and to-dos of the user's own ("Book the hotel").
A plan is finished when the user says so, or when every save and to-do is
ticked.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.items_repo import decode_json_list, update_item

MAX_NAME = 80
MAX_ITEMS = 200
MAX_TASKS = 200
MAX_SECTION = 40
COLORS = ("accent", "violet", "indigo", "blue", "teal", "emerald", "amber", "rose", "zinc")  # accent: follows the app's accent colour


def clean_section(section: str | None) -> str | None:
    return " ".join(str(section or "").split())[:MAX_SECTION] or None


def clean_date(value: str | None) -> str | None:
    """A day as "2026-12-24", or None. Raises ValueError for anything else."""
    if not value:
        return None
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date().isoformat()


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_name(name: str) -> str:
    return " ".join(str(name).split())[:MAX_NAME]


def exists(conn: sqlite3.Connection, plan_id: int) -> bool:
    return conn.execute("SELECT 1 FROM plans WHERE id = ?", (plan_id,)).fetchone() is not None


def create(conn: sqlite3.Connection, name: str, note: str | None = None, item_ids: list[int] | None = None) -> int:
    name = clean_name(name)
    if not name:
        raise ValueError("A plan needs a name.")
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM plans").fetchone()[0]
    plan_id = int(conn.execute(
        "INSERT INTO plans (name, note, position) VALUES (?, ?, ?)", (name, (note or "").strip()[:500] or None, position)
    ).lastrowid or 0)
    if item_ids:
        add_items(conn, plan_id, item_ids)
    return plan_id


def update(conn: sqlite3.Connection, plan_id: int, **fields: Any) -> None:
    sets: dict[str, Any] = {}
    if "name" in fields and fields["name"] is not None:
        name = clean_name(fields["name"])
        if not name:
            raise ValueError("A plan needs a name.")
        sets["name"] = name
    if "note" in fields:
        sets["note"] = (fields["note"] or "").strip()[:500] or None
    if "color" in fields:
        if fields["color"] not in (None, *COLORS):
            raise ValueError("Unknown colour.")
        sets["color"] = fields["color"]
    if "done" in fields and fields["done"] is not None:
        sets["done_at"] = now_iso() if fields["done"] else None
    if "due_on" in fields:
        try:
            sets["due_on"] = clean_date(fields["due_on"])
        except ValueError as error:
            raise ValueError("That isn't a date.") from error
    if "pinned" in fields and fields["pinned"] is not None:
        sets["pinned"] = int(bool(fields["pinned"]))
    if sets:
        sets["updated_at"] = now_iso()
        conn.execute(
            f"UPDATE plans SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), plan_id)
        )


def delete(conn: sqlite3.Connection, plan_id: int) -> None:
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))


def add_items(conn: sqlite3.Connection, plan_id: int, item_ids: list[int]) -> int:
    """Add saves at the end of the plan (ones already in it stay where they are)."""
    have = int(conn.execute("SELECT COUNT(*) FROM plan_items WHERE plan_id = ?", (plan_id,)).fetchone()[0])
    added = 0
    position = int(conn.execute(
        "SELECT COALESCE(MAX(position), 0) FROM plan_items WHERE plan_id = ?", (plan_id,)
    ).fetchone()[0])
    for item_id in dict.fromkeys(item_ids):
        if have + added >= MAX_ITEMS:
            raise ValueError(f"A plan can hold up to {MAX_ITEMS} saves.")
        if not conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            continue
        position += 1
        cursor = conn.execute(
            "INSERT OR IGNORE INTO plan_items (plan_id, item_id, position) VALUES (?, ?, ?)",
            (plan_id, item_id, position),
        )
        if cursor.rowcount:
            added += 1
            started = conn.execute("SELECT started_at FROM items WHERE id = ?", (item_id,)).fetchone()
            if started and not started["started_at"]:
                update_item(conn, item_id, started_at=now_iso())
    if added:
        _reopen_if_needed(conn, plan_id)
        conn.execute("UPDATE plans SET updated_at = ? WHERE id = ?", (now_iso(), plan_id))
    return added


def remove_item(conn: sqlite3.Connection, plan_id: int, item_id: int) -> None:
    conn.execute("DELETE FROM plan_items WHERE plan_id = ? AND item_id = ?", (plan_id, item_id))


def tick_item(conn: sqlite3.Connection, plan_id: int, item_id: int, done: bool) -> None:
    """Tick a save off in this plan. When every save is ticked the plan is finished."""
    cursor = conn.execute(
        "UPDATE plan_items SET done = ?, done_at = ? WHERE plan_id = ? AND item_id = ?",
        (int(done), now_iso() if done else None, plan_id, item_id),
    )
    if not cursor.rowcount:
        raise KeyError("That save isn't in this plan.")
    _finish_if_all_ticked(conn, plan_id)


def _finish_if_all_ticked(conn: sqlite3.Connection, plan_id: int) -> None:
    """Finished when nothing is left unticked (saves and to-dos); open again otherwise."""
    left = int(conn.execute(
        "SELECT (SELECT COUNT(*) FROM plan_items WHERE plan_id = ? AND done = 0) + "
        "(SELECT COUNT(*) FROM plan_tasks WHERE plan_id = ? AND done = 0)", (plan_id, plan_id)
    ).fetchone()[0])
    conn.execute(
        "UPDATE plans SET done_at = CASE WHEN ? = 0 THEN coalesce(done_at, ?) ELSE NULL END, updated_at = ? WHERE id = ?",
        (left, now_iso(), now_iso(), plan_id),
    )


def set_item(conn: sqlite3.Connection, plan_id: int, item_id: int, **fields: Any) -> None:
    """Change a save's section or note in this plan."""
    sets: dict[str, Any] = {}
    if "section" in fields:
        sets["section"] = clean_section(fields["section"])
    if "note" in fields:
        sets["note"] = (fields["note"] or "").strip()[:300] or None
    if not sets:
        return
    cursor = conn.execute(
        f"UPDATE plan_items SET {', '.join(f'{k} = ?' for k in sets)} WHERE plan_id = ? AND item_id = ?",
        (*sets.values(), plan_id, item_id),
    )
    if not cursor.rowcount:
        raise KeyError("That save isn't in this plan.")
    conn.execute("UPDATE plans SET updated_at = ? WHERE id = ?", (now_iso(), plan_id))


def rename_section(conn: sqlite3.Connection, plan_id: int, old: str, new: str | None) -> None:
    """Rename a section (or with new None, dissolve it: its things stay, unsectioned)."""
    target = clean_section(new)
    for table in ("plan_items", "plan_tasks"):
        conn.execute(f"UPDATE {table} SET section = ? WHERE plan_id = ? AND section = ?", (target, plan_id, old))


# ---------- the user's own to-dos ----------


def tasks(conn: sqlite3.Connection, plan_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, text, section, done, done_at FROM plan_tasks WHERE plan_id = ? ORDER BY position, id", (plan_id,)
    ).fetchall()
    return [dict(row) | {"done": bool(row["done"])} for row in rows]


def add_task(conn: sqlite3.Connection, plan_id: int, text: str, section: str | None = None) -> int:
    text = " ".join(str(text).split())[:200]
    if not text:
        raise ValueError("Type what needs doing.")
    if int(conn.execute("SELECT COUNT(*) FROM plan_tasks WHERE plan_id = ?", (plan_id,)).fetchone()[0]) >= MAX_TASKS:
        raise ValueError(f"A plan can hold up to {MAX_TASKS} to-dos.")
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM plan_tasks WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    task_id = int(conn.execute(
        "INSERT INTO plan_tasks (plan_id, text, section, position) VALUES (?, ?, ?, ?)",
        (plan_id, text, clean_section(section), position),
    ).lastrowid or 0)
    _finish_if_all_ticked(conn, plan_id)  # a new to-do reopens a finished plan
    return task_id


def update_task(conn: sqlite3.Connection, plan_id: int, task_id: int, **fields: Any) -> None:
    sets: dict[str, Any] = {}
    if fields.get("text") is not None:
        text = " ".join(str(fields["text"]).split())[:200]
        if not text:
            raise ValueError("Type what needs doing.")
        sets["text"] = text
    if "section" in fields:
        sets["section"] = clean_section(fields["section"])
    if fields.get("done") is not None:
        sets["done"] = int(bool(fields["done"]))
        sets["done_at"] = now_iso() if fields["done"] else None
    if not sets:
        return
    cursor = conn.execute(
        f"UPDATE plan_tasks SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ? AND plan_id = ?",
        (*sets.values(), task_id, plan_id),
    )
    if not cursor.rowcount:
        raise KeyError("That to-do isn't in this plan.")
    if "done" in sets:
        _finish_if_all_ticked(conn, plan_id)


def delete_task(conn: sqlite3.Connection, plan_id: int, task_id: int) -> None:
    conn.execute("DELETE FROM plan_tasks WHERE id = ? AND plan_id = ?", (task_id, plan_id))


def copy(conn: sqlite3.Connection, plan_id: int) -> int:
    """A fresh copy of a plan: same saves, sections, notes and to-dos, nothing ticked."""
    row = get(conn, plan_id)
    if row is None:
        raise KeyError("That plan doesn't exist any more.")
    new_id = create(conn, f"{row['name']} (copy)"[:MAX_NAME], row["note"])
    conn.execute("UPDATE plans SET color = ? WHERE id = ?", (row["color"], new_id))
    conn.execute(
        "INSERT INTO plan_items (plan_id, item_id, position, section, note) "
        "SELECT ?, item_id, position, section, note FROM plan_items WHERE plan_id = ?", (new_id, plan_id)
    )
    conn.execute(
        "INSERT INTO plan_tasks (plan_id, text, section, position) "
        "SELECT ?, text, section, position FROM plan_tasks WHERE plan_id = ?", (new_id, plan_id)
    )
    return new_id


def reorder(conn: sqlite3.Connection, plan_id: int, item_ids: list[int]) -> None:
    current = [int(r["item_id"]) for r in conn.execute(
        "SELECT item_id FROM plan_items WHERE plan_id = ? ORDER BY position, added_at", (plan_id,)
    )]
    ordered = [i for i in dict.fromkeys(item_ids) if i in current] + [i for i in current if i not in item_ids]
    for position, item_id in enumerate(ordered, start=1):
        conn.execute("UPDATE plan_items SET position = ? WHERE plan_id = ? AND item_id = ?", (position, plan_id, item_id))


def _reopen_if_needed(conn: sqlite3.Connection, plan_id: int) -> None:
    """A finished plan that gets a new, unticked save is open again."""
    conn.execute(
        "UPDATE plans SET done_at = NULL WHERE id = ? AND EXISTS "
        "(SELECT 1 FROM plan_items WHERE plan_id = ? AND done = 0)",
        (plan_id, plan_id),
    )


def _step_counts(conn: sqlite3.Connection, item_ids: list[int]) -> tuple[int, int]:
    if not item_ids:
        return 0, 0
    marks = ",".join("?" for _ in item_ids)
    done = total = 0
    for row in conn.execute(f"SELECT steps_json FROM ai_results WHERE item_id IN ({marks})", item_ids):
        for step in decode_json_list(row["steps_json"]):
            total += 1
            done += bool(isinstance(step, dict) and step.get("done"))
    return done, total


def summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """A plan for the list: name, progress and the first few pictures."""
    items = conn.execute(
        """SELECT pi.item_id, pi.done, i.thumbnail_path IS NOT NULL AS has_thumbnail, i.platform
           FROM plan_items pi JOIN items i ON i.id = pi.item_id AND i.deleted_at IS NULL
           WHERE pi.plan_id = ? ORDER BY pi.position, pi.added_at""",
        (row["id"],),
    ).fetchall()
    ids = [int(r["item_id"]) for r in items]
    steps_done, steps_total = _step_counts(conn, ids)
    todo = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM plan_tasks WHERE plan_id = ?", (row["id"],)
    ).fetchone()
    return {
        "due_on": row["due_on"],
        "pinned": bool(row["pinned"]),
        "tasks_total": int(todo["total"]),
        "tasks_done": int(todo["done"]),
        "id": int(row["id"]),
        "name": row["name"],
        "note": row["note"],
        "color": row["color"],
        "done": row["done_at"] is not None,
        "done_at": row["done_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "item_count": len(ids),
        "items_done": sum(int(r["done"]) for r in items),
        "steps_done": steps_done,
        "steps_total": steps_total,
        "preview": [{"id": int(r["item_id"]), "has_thumbnail": bool(r["has_thumbnail"])} for r in items[:4]],
        "platforms": sorted({str(r["platform"]) for r in items}),
    }


def list_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # Open ones first: pinned, then the soonest day, then the user's order.
    rows = conn.execute(
        "SELECT * FROM plans ORDER BY done_at IS NOT NULL, pinned DESC, due_on IS NULL, due_on, position, id"
    ).fetchall()
    return [summary(conn, row) for row in rows]


def get(conn: sqlite3.Connection, plan_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()  # type: ignore[no-any-return]


def item_rows(conn: sqlite3.Connection, plan_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT item_id, done, done_at, position, section, note FROM plan_items WHERE plan_id = ? ORDER BY position, added_at",
        (plan_id,),
    ).fetchall()
