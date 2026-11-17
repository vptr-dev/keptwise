"""Tags: short topic words on each save ("pasta", "london", "gcse").

Every tag on an item remembers where it came from (`source`):
  user - the user added it (never removed by the app)
  ai   - written by the AI with the notes (replaced when notes are redone)
  rule - one of the user's rules ("anything mentioning Japan gets #japan")
  auto - the "not in any collection" tag, added and removed by the app
Tag names are lowercase, without "#", and unique whatever the case.
"""

from __future__ import annotations

import sqlite3
from typing import Any

MAX_TAG = 40
# A save has at most this many tags (the automatic "unsorted" one doesn't
# count), and the app has at most MAX_TAGS different tags.
MAX_PER_ITEM = 10
MAX_TAGS = 100


class SaveFull(ValueError):
    """The save already has the most tags allowed."""


class TagsFull(ValueError):
    """The app already has the most different tags allowed."""


def total(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0])


def full_message() -> str:
    return (
        f"You have {MAX_TAGS} tags, the most the app allows. Use one you already have, "
        "or merge or delete some on the Tags page."
    )


def clean_tag(name: str) -> str:
    return " ".join(str(name).strip().lstrip("#").split()).lower()[:MAX_TAG]


def find(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tags WHERE name = ?", (clean_tag(name),)).fetchone()  # type: ignore[no-any-return]


def ensure(conn: sqlite3.Connection, name: str, over_limit: bool = False) -> int:
    """The id of the tag with this name, creating it if needed. Raises
    TagsFull when a new one would go over MAX_TAGS (over_limit: the app's
    own "unsorted" tag may)."""
    name = clean_tag(name)
    if not name:
        raise ValueError("A tag needs a name.")
    row = find(conn, name)
    if row:
        return int(row["id"])
    if not over_limit and total(conn) >= MAX_TAGS:
        raise TagsFull(full_message())
    return int(conn.execute("INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid or 0)


def list_all(conn: sqlite3.Connection, platform: str | None = None) -> list[dict[str, Any]]:
    """Every tag with how many saves have it (only that platform's when one
    is picked), most used first, and who added it (user, ai, the app)."""
    # Counted from the link table alone (index item_tags_count); the saves
    # themselves are only looked at to leave out deleted ones, which are few,
    # and to keep to one platform.
    only = " AND it.item_id IN (SELECT id FROM items WHERE platform = ?)" if platform else ""
    rows = conn.execute(
        f"""SELECT t.id, t.name, t.color, t.created_at, COALESCE(n.count, 0) AS count,
                  n.by_user, n.by_ai, n.by_app
           FROM tags t LEFT JOIN (
               SELECT it.tag_id, COUNT(*) AS count,
                      SUM(it.source = 'user') AS by_user,
                      SUM(it.source = 'ai') AS by_ai,
                      SUM(it.source IN ('rule', 'auto')) AS by_app
               FROM item_tags it
               WHERE it.item_id NOT IN (SELECT id FROM items WHERE deleted_at IS NOT NULL){only}
               GROUP BY it.tag_id
           ) n ON n.tag_id = t.id
           ORDER BY count DESC, t.name""",
        [platform] if platform else [],
    ).fetchall()
    out = []
    for row in rows:
        tag = dict(row)
        for key in ("by_user", "by_ai", "by_app"):
            tag[key] = int(tag[key] or 0)
        out.append(tag)
    return out


def of_item(conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT t.id, t.name, t.color, it.source FROM item_tags it JOIN tags t ON t.id = it.tag_id
           WHERE it.item_id = ? ORDER BY it.source = 'auto', it.created_at, t.name""",
        (item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def count_on(conn: sqlite3.Connection, item_id: int) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM item_tags WHERE item_id = ? AND source <> 'auto'", (item_id,)
    ).fetchone()[0])


def add(conn: sqlite3.Connection, item_id: int, name: str, source: str = "user") -> int:
    """Put a tag on an item. The user's own choice wins over the app's.
    Raises SaveFull when the save already has MAX_PER_ITEM tags, and
    TagsFull when it's a new tag and the app has MAX_TAGS already."""
    existing = find(conn, name)
    already = existing is not None and conn.execute(
        "SELECT 1 FROM item_tags WHERE item_id = ? AND tag_id = ?", (item_id, int(existing["id"]))
    ).fetchone() is not None
    if not already and source != "auto" and count_on(conn, item_id) >= MAX_PER_ITEM:
        raise SaveFull(f"A save can have up to {MAX_PER_ITEM} tags. Remove one first.")
    tag_id = ensure(conn, name, over_limit=source == "auto")
    conn.execute(
        """INSERT INTO item_tags (item_id, tag_id, source) VALUES (?, ?, ?)
           ON CONFLICT (item_id, tag_id) DO UPDATE SET source = CASE WHEN excluded.source = 'user'
               THEN 'user' ELSE item_tags.source END""",
        (item_id, tag_id, source),
    )
    return tag_id


def remove(conn: sqlite3.Connection, item_id: int, tag_id: int) -> None:
    conn.execute("DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?", (item_id, tag_id))


def replace_source(conn: sqlite3.Connection, item_id: int, names: list[str], source: str) -> None:
    """Swap all of one source's tags on an item (e.g. the AI's) for new ones.
    Tags from other sources stay."""
    conn.execute("DELETE FROM item_tags WHERE item_id = ? AND source = ?", (item_id, source))
    for name in names:
        if clean_tag(name):
            try:
                add(conn, item_id, name, source)
            except SaveFull:
                break  # the save is full: the user's own tags come first
            except TagsFull:
                continue  # no room for new tags: only ones that exist are used


def rename(conn: sqlite3.Connection, tag_id: int, name: str) -> int:
    """Rename a tag. If another tag already has that name, the two are
    merged into that one. Returns the id of the tag that is left."""
    name = clean_tag(name)
    if not name:
        raise ValueError("A tag needs a name.")
    other = find(conn, name)
    if other is None or int(other["id"]) == tag_id:
        conn.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
        return tag_id
    target = int(other["id"])
    conn.execute(
        "INSERT OR IGNORE INTO item_tags (item_id, tag_id, source, created_at) "
        "SELECT item_id, ?, source, created_at FROM item_tags WHERE tag_id = ?",
        (target, tag_id),
    )
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    return target


def set_color(conn: sqlite3.Connection, tag_id: int, color: str | None) -> None:
    conn.execute("UPDATE tags SET color = ? WHERE id = ?", (color, tag_id))


def delete(conn: sqlite3.Connection, tag_id: int) -> None:
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


def drop_unused(conn: sqlite3.Connection) -> None:
    """Remove tags no save has any more (the AI's old words, mostly).
    Tags the user picked a colour for are kept."""
    conn.execute(
        "DELETE FROM tags WHERE color IS NULL AND NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.tag_id = tags.id)"
    )


# ---------- the "not in any collection" tag ----------


def sync_no_collection(conn: sqlite3.Connection, item_id: int, tag_name: str) -> None:
    """Give a save with AI notes but no collection the chosen tag, and take
    it off again once it is in a collection. Empty tag_name = switched off."""
    conn.execute("DELETE FROM item_tags WHERE item_id = ? AND source = 'auto'", (item_id,))
    if not clean_tag(tag_name):
        return
    row = conn.execute(
        """SELECT i.status = 'processed' AND NOT EXISTS
               (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id) AS wanted
           FROM items i WHERE i.id = ?""",
        (item_id,),
    ).fetchone()
    if row and row["wanted"]:
        add(conn, item_id, tag_name, "auto")


def sync_all_no_collection(conn: sqlite3.Connection, tag_name: str) -> None:
    """Do sync_no_collection for every save (after the setting changes)."""
    conn.execute("DELETE FROM item_tags WHERE source = 'auto'")
    if clean_tag(tag_name):
        tag_id = ensure(conn, tag_name, over_limit=True)
        conn.execute(
            """INSERT OR IGNORE INTO item_tags (item_id, tag_id, source)
               SELECT i.id, ?, 'auto' FROM items i WHERE i.status = 'processed' AND NOT EXISTS
                   (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id)""",
            (tag_id,),
        )
    drop_unused(conn)
