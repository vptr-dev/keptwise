"""Links from a platform's collections to the app's collections.

"From TikTok collection 'recipes', add to my Food". The user picks the app
collection for each platform collection, and how:

- auto: every save from it is filed there now, and again after each import
  and re-sort, by itself.
- manual: nothing happens until the user presses "Add now".

Links never make collections (the app has at most 10, chosen by the user),
and never take a save out of a collection the user put it in.

Not every export says which saves are in which collection: YouTube,
Instagram and Facebook do, TikTok only lists the names. A TikTok name can
still be linked, so the AI uses it as a hint, but there is nothing to copy.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Literal

from app.ai.sorting.collections import add_from_platform, clean_name, names_from_imports
from app.importers import PLATFORM_NAMES

Mode = Literal["auto", "manual"]


def split_names(raw: str | None) -> list[str]:
    """The importer joins several platform collections with ', '."""
    return [clean_name(name) for name in str(raw or "").split(", ") if clean_name(name)]


def _member_counts(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, int]]:
    """(platform, lowercase name) -> (name as written, number of saves)."""
    counts: dict[tuple[str, str], tuple[str, int]] = {}
    rows = conn.execute(
        "SELECT platform, platform_collection FROM items WHERE platform_collection IS NOT NULL AND platform_collection <> ''"
    ).fetchall()
    for row in rows:
        for name in split_names(row["platform_collection"]):
            key = (str(row["platform"]), name.lower())
            shown, number = counts.get(key, (name, 0))
            counts[key] = (shown, number + 1)
    return counts


def _members(conn: sqlite3.Connection, platform: str, name: str) -> list[int]:
    """The saves the export says are in this platform collection."""
    wanted = clean_name(name).lower()
    rows = conn.execute(
        "SELECT id, platform_collection FROM items WHERE platform = ? AND platform_collection LIKE ?",
        (platform, f"%{wanted}%"),
    ).fetchall()
    return [int(row["id"]) for row in rows if wanted in {n.lower() for n in split_names(row["platform_collection"])}]


def overview(conn: sqlite3.Connection, platform: str | None = None) -> list[dict[str, Any]]:
    """Every platform collection the imports found, with its link (if any)."""
    counts = _member_counts(conn)
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for (plat, lower), (name, number) in counts.items():
        entries[(plat, lower)] = {"platform": plat, "name": name, "count": number, "membership_known": True}
    for plat, name in names_from_imports(conn):
        entries.setdefault(
            (plat, name.lower()), {"platform": plat, "name": name, "count": 0, "membership_known": False}
        )
    links = {
        (str(row["platform"]), str(row["name"]).lower()): row
        for row in conn.execute(
            """SELECT l.platform, l.name, l.mode, l.collection_id, c.name AS collection_name
               FROM platform_links l LEFT JOIN collections c ON c.id = l.collection_id"""
        )
    }
    out = []
    for key, entry in entries.items():
        if platform and entry["platform"] != platform:
            continue
        link = links.get(key)
        filed = 0
        if link and link["collection_id"] and entry["count"]:
            ids = _members(conn, entry["platform"], entry["name"])
            marks = ",".join("?" for _ in ids)
            filed = int(conn.execute(
                f"SELECT COUNT(*) FROM item_collections WHERE collection_id = ? AND item_id IN ({marks})",
                (link["collection_id"], *ids),
            ).fetchone()[0])
        out.append(entry | {
            "platform_name": PLATFORM_NAMES.get(entry["platform"], entry["platform"]),
            "collection_id": link["collection_id"] if link else None,
            "collection_name": link["collection_name"] if link else None,
            "mode": link["mode"] if link else "auto",
            "filed": filed,
        })
    out.sort(key=lambda e: (e["platform"], -e["count"], e["name"].lower()))
    return out


def set_link(conn: sqlite3.Connection, platform: str, name: str, collection_id: int | None, mode: Mode) -> int:
    """Link (or with collection_id None, unlink) a platform collection.
    An auto link files its saves straight away; returns how many."""
    name = clean_name(name)
    if not name:
        raise ValueError("Which platform collection?")
    if collection_id is None:
        conn.execute("DELETE FROM platform_links WHERE platform = ? AND name = ?", (platform, name))
        return 0
    conn.execute(
        """INSERT INTO platform_links (platform, name, collection_id, mode) VALUES (?, ?, ?, ?)
           ON CONFLICT (platform, name) DO UPDATE SET collection_id = excluded.collection_id, mode = excluded.mode""",
        (platform, name, collection_id, mode),
    )
    return apply(conn, platform, name) if mode == "auto" else 0


def apply(conn: sqlite3.Connection, platform: str, name: str) -> int:
    """File the saves of one linked platform collection now (the "Add now" button)."""
    row = conn.execute(
        "SELECT collection_id FROM platform_links WHERE platform = ? AND name = ?", (platform, clean_name(name))
    ).fetchone()
    if row is None or row["collection_id"] is None:
        raise ValueError("Pick a collection in the app for it first.")
    return sum(add_from_platform(conn, item_id, int(row["collection_id"])) for item_id in _members(conn, platform, name))


def apply_all_auto(conn: sqlite3.Connection) -> int:
    """Run every auto link (after an import). Returns how many saves were filed."""
    rows = conn.execute(
        "SELECT platform, name FROM platform_links WHERE mode = 'auto' AND collection_id IS NOT NULL"
    ).fetchall()
    return sum(apply(conn, str(row["platform"]), str(row["name"])) for row in rows)


def linked_collections(conn: sqlite3.Connection, item: dict[str, Any]) -> list[str]:
    """The app collections this save's platform collections are auto-linked to."""
    wanted = [name.lower() for name in split_names(item.get("platform_collection"))]
    if not wanted:
        return []
    rows = conn.execute(
        """SELECT l.name, c.name AS collection FROM platform_links l JOIN collections c ON c.id = l.collection_id
           WHERE l.platform = ? AND l.mode = 'auto'""",
        (item.get("platform"),),
    ).fetchall()
    out: list[str] = []
    for row in rows:
        if str(row["name"]).lower() in wanted and row["collection"] not in out:
            out.append(str(row["collection"]))
    return out
