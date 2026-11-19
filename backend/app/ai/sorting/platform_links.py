"""Links from a platform's collections to the app's collections.

"From TikTok collection 'recipes', add to my Food". The user picks the app
collection for each platform collection, and how:

- auto: file current saves when the user creates the link, and file newly
  discovered members on subsequent imports.
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
from app.db.items_repo import decode_json_list
from app.importers import PLATFORM_NAMES

Mode = Literal["auto", "manual"]


def member_names(row: sqlite3.Row) -> list[str]:
    """Older imports supply only a display string; new ones retain exact names."""
    raw = row["platform_collections_json"]
    names = decode_json_list(raw) if raw is not None else (row["platform_collection"] or "").split(", ")
    return [clean_name(name) for name in names if isinstance(name, str) and clean_name(name)]


def _member_counts(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, int]]:
    """(platform, lowercase name) -> (name as written, number of saves)."""
    counts: dict[tuple[str, str], tuple[str, int]] = {}
    for row in conn.execute(
        """SELECT platform, platform_collection, platform_collections_json FROM items
           WHERE platform_collection IS NOT NULL AND deleted_at IS NULL AND gone_at IS NULL ORDER BY id"""
    ):
        for lower, name in {name.casefold(): name for name in member_names(row)}.items():
            key = (str(row["platform"]), lower)
            shown, number = counts.get(key, (name, 0))
            counts[key] = (shown, number + 1)
    return counts


def _members(conn: sqlite3.Connection, platform: str, name: str, collection_id: int | None = None) -> list[int]:
    """The saves the export says are in this platform collection."""
    wanted = clean_name(name).casefold()
    query = """SELECT i.id, i.platform_collection, i.platform_collections_json FROM items i WHERE i.platform = ?
               AND i.platform_collection IS NOT NULL AND i.deleted_at IS NULL AND i.gone_at IS NULL"""
    params: tuple[str | int, ...] = (platform,)
    if collection_id is not None:
        query += " AND EXISTS (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id AND ic.collection_id = ?)"
        params += (collection_id,)
    return [
        int(row["id"]) for row in conn.execute(query, params)
        if wanted in {name.casefold() for name in member_names(row)}
    ]


def overview(conn: sqlite3.Connection, platform: str | None = None) -> list[dict[str, Any]]:
    """Every platform collection the imports found, with its link (if any)."""
    counts = _member_counts(conn)
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for (plat, lower), (name, number) in counts.items():
        entries[(plat, lower)] = {"platform": plat, "name": name, "count": number, "membership_known": True}
    for plat, name in names_from_imports(conn):
        entries.setdefault(
            (plat, name.casefold()), {"platform": plat, "name": name, "count": 0, "membership_known": False}
        )
    links = {
        (str(row["platform"]), str(row["name"]).casefold()): row
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
            filed = len(_members(conn, entry["platform"], entry["name"], link["collection_id"]))
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
    existing = next((
        row for row in conn.execute("SELECT * FROM platform_links WHERE platform = ?", (platform,))
        if row["name"].casefold() == name.casefold()
    ), None)
    if existing is not None:
        name = existing["name"]
    if collection_id is None:
        conn.execute("DELETE FROM platform_links WHERE platform = ? AND name = ?", (platform, name))
        return 0
    conn.execute(
        """INSERT INTO platform_links (platform, name, collection_id, mode) VALUES (?, ?, ?, ?)
           ON CONFLICT (platform, name) DO UPDATE SET collection_id = excluded.collection_id, mode = excluded.mode""",
        (platform, name, collection_id, mode),
    )
    changed = existing is None or existing["collection_id"] != collection_id or existing["mode"] != mode
    return apply(conn, platform, name) if mode == "auto" and changed else 0


def apply(conn: sqlite3.Connection, platform: str, name: str) -> int:
    """File the saves of one linked platform collection now (the "Add now" button)."""
    row = conn.execute(
        "SELECT collection_id FROM platform_links WHERE platform = ? AND name = ?", (platform, clean_name(name))
    ).fetchone()
    if row is None or row["collection_id"] is None:
        raise ValueError("Pick a collection in the app for it first.")
    return sum(add_from_platform(conn, item_id, int(row["collection_id"])) for item_id in _members(conn, platform, name))


def import_destinations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    defaults = dict(conn.execute("SELECT platform, collection_id FROM platform_import_destinations"))
    return [
        {"platform": platform, "platform_name": name, "collection_id": defaults.get(platform)}
        for platform, name in PLATFORM_NAMES.items()
    ]


def set_import_destination(conn: sqlite3.Connection, platform: str, collection_id: int | None) -> None:
    if collection_id is None:
        conn.execute("DELETE FROM platform_import_destinations WHERE platform = ?", (platform,))
    else:
        conn.execute(
            """INSERT INTO platform_import_destinations (platform, collection_id) VALUES (?, ?)
               ON CONFLICT (platform) DO UPDATE SET collection_id = excluded.collection_id""",
            (platform, collection_id),
        )


def import_routes(conn: sqlite3.Connection, platform: str) -> tuple[dict[str, int], int | None]:
    exact = {
        row["name"].casefold(): row["collection_id"]
        for row in conn.execute(
            """SELECT name, collection_id FROM platform_links
               WHERE platform = ? AND mode = 'auto' AND collection_id IS NOT NULL""",
            (platform,),
        )
    }
    default = conn.execute(
        "SELECT collection_id FROM platform_import_destinations WHERE platform = ?", (platform,)
    ).fetchone()
    return exact, default["collection_id"] if default else None
