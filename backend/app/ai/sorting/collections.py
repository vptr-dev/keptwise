"""The app's own collections and which items are in them.

Every link between an item and a collection remembers who made it
(`source`): "user" (the user put it there or approved it), "rule" (one of
the user's rules), "ai", or "platform" (from a platform collection the
user linked, e.g. TikTok "recipes" -> Food). Re-sorting replaces the AI's,
rules' and platforms' links, and never touches the user's own.

Collections live in spaces ("My saves", "Work", ...; tabs at the top of the
Collections page) and can sit inside each other like folders, up to
MAX_DEPTH levels. A space holds at most MAX_COLLECTIONS of them, and one
save can be in up to MAX_PER_ITEM. Tags are for the small details. Names are
unique across the whole app, whatever the case, because sorting and rules
find a collection by its name. Sorting only ever files into collections that
exist: the app never makes collections by itself.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.db.connection import Database
from app.db.settings_repo import SettingsRepo

SEEDED_KEY = "sorting.seeded"
# The list the user starts with: broad topics, renamed or deleted at will.
STARTER_COLLECTIONS = ["Food", "Travel", "Fitness", "Shopping", "Home & DIY", "Learning", "Fun"]
MAX_NAME = 80
MAX_COLLECTIONS = 50  # in one space
MAX_PER_ITEM = 10  # collections one save can be in
MAX_SPACES = 8
MAX_DEPTH = 5  # a collection inside a collection inside ... this many levels


class SaveFull(ValueError):
    """The save is already in the most collections allowed."""
COLORS = ("accent", "violet", "indigo", "blue", "teal", "emerald", "amber", "rose", "zinc")  # accent: follows the app's accent colour


@dataclass(frozen=True)
class Link:
    """One item-in-collection decision."""

    name: str
    source: str  # user, rule, ai, platform
    confidence: float | None = None
    origin: str = "mine"


def clean_name(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME]


def find(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute(  # type: ignore[no-any-return]
        "SELECT * FROM collections WHERE name = ? COLLATE NOCASE", (clean_name(name),)
    ).fetchone()


# ---------- spaces ----------


def spaces(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every space in the user's order, with how many collections it holds."""
    rows = conn.execute(
        """SELECT s.id, s.name, s.color, s.position, COUNT(c.id) AS collections
           FROM spaces s LEFT JOIN collections c ON c.space_id = s.id
           GROUP BY s.id ORDER BY s.position, s.id"""
    ).fetchall()
    return [dict(row) for row in rows]


def default_space(conn: sqlite3.Connection) -> int:
    """The first space; made again if every space was somehow lost."""
    row = conn.execute("SELECT id FROM spaces ORDER BY position, id LIMIT 1").fetchone()
    if row:
        return int(row["id"])
    return int(conn.execute("INSERT INTO spaces (name, position) VALUES ('My saves', 1)").lastrowid or 0)


def space_exists(conn: sqlite3.Connection, space_id: int) -> bool:
    return conn.execute("SELECT 1 FROM spaces WHERE id = ?", (space_id,)).fetchone() is not None


def _space_name(conn: sqlite3.Connection, name: str, space_id: int | None = None) -> str:
    name = clean_name(name)[:40]
    if not name:
        raise ValueError("A space needs a name.")
    other = conn.execute("SELECT id FROM spaces WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if other and int(other["id"]) != space_id:
        raise ValueError(f"There's already a space called “{name}”.")
    return name


def create_space(conn: sqlite3.Connection, name: str) -> int:
    name = _space_name(conn, name)
    if int(conn.execute("SELECT COUNT(*) FROM spaces").fetchone()[0]) >= MAX_SPACES:
        raise ValueError(f"You can have up to {MAX_SPACES} spaces. Delete or reuse one first.")
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM spaces").fetchone()[0]
    return int(conn.execute("INSERT INTO spaces (name, position) VALUES (?, ?)", (name, position)).lastrowid or 0)


def update_space(conn: sqlite3.Connection, space_id: int, name: str | None = None, color: str | None = None,
                 clear_color: bool = False) -> None:
    if name is not None:
        conn.execute("UPDATE spaces SET name = ? WHERE id = ?", (_space_name(conn, name, space_id), space_id))
    if color is not None or clear_color:
        if color is not None and color not in COLORS:
            raise ValueError("Unknown colour.")
        conn.execute("UPDATE spaces SET color = ? WHERE id = ?", (None if clear_color else color, space_id))


def delete_space(conn: sqlite3.Connection, space_id: int) -> int:
    """Delete a space. Its collections aren't lost: they move to the first
    other space, keeping their folders. Returns that space's id."""
    others = [int(r["id"]) for r in conn.execute("SELECT id FROM spaces WHERE id != ? ORDER BY position, id", (space_id,))]
    if not others:
        raise ValueError("This is your only space. Make another one before deleting it.")
    target = others[0]
    moving = int(conn.execute("SELECT COUNT(*) FROM collections WHERE space_id = ?", (space_id,)).fetchone()[0])
    if moving and count(conn, target) + moving > MAX_COLLECTIONS:
        raise ValueError(
            f"Its {moving} collections don't fit in the other space (up to {MAX_COLLECTIONS} each). "
            "Move or delete some first."
        )
    last = conn.execute("SELECT COALESCE(MAX(position), 0) FROM collections WHERE space_id = ?", (target,)).fetchone()[0]
    conn.execute("UPDATE collections SET space_id = ?, position = position + ? WHERE space_id = ?", (target, last, space_id))
    conn.execute("DELETE FROM spaces WHERE id = ?", (space_id,))
    return target


def place_space(conn: sqlite3.Connection, space_id: int, index: int) -> None:
    others = [int(r["id"]) for r in conn.execute("SELECT id FROM spaces WHERE id != ? ORDER BY position, id", (space_id,))]
    others.insert(max(0, min(index, len(others))), space_id)
    for position, other in enumerate(others, start=1):
        conn.execute("UPDATE spaces SET position = ? WHERE id = ?", (position, other))


# ---------- collections ----------


def count(conn: sqlite3.Connection, space_id: int | None = None) -> int:
    """How many collections a space holds (the first space when not given)."""
    space_id = default_space(conn) if space_id is None else space_id
    return int(conn.execute("SELECT COUNT(*) FROM collections WHERE space_id = ?", (space_id,)).fetchone()[0])


def room_left(conn: sqlite3.Connection, space_id: int | None = None) -> int:
    return max(0, MAX_COLLECTIONS - count(conn, space_id))


def count_on(conn: sqlite3.Connection, item_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM item_collections WHERE item_id = ?", (item_id,)).fetchone()[0])


def has_link(conn: sqlite3.Connection, item_id: int, collection_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM item_collections WHERE item_id = ? AND collection_id = ?", (item_id, collection_id)
    ).fetchone() is not None


def save_full_message() -> str:
    return f"A save can be in up to {MAX_PER_ITEM} collections. Take it out of one first."


def full_message() -> str:
    return (
        f"This space already has {MAX_COLLECTIONS} collections, the most a space can hold. Use tags for the "
        "smaller details, merge or delete a collection, or put the new one in another space."
    )


def ensure(conn: sqlite3.Connection, name: str, origin: str = "mine", parent_id: int | None = None,
           space_id: int | None = None) -> int:
    """The id of the collection with this name, creating it if needed: inside
    parent_id when given, else at the top of space_id (the first space when
    not given). Raises ValueError when that space is full."""
    name = clean_name(name)
    if not name:
        raise ValueError("A collection needs a name.")
    row = find(conn, name)
    if row:
        return int(row["id"])
    parent = conn.execute("SELECT id, space_id FROM collections WHERE id = ?", (parent_id,)).fetchone() if parent_id else None
    if parent:
        space_id = int(parent["space_id"])
    elif space_id is None or not space_exists(conn, space_id):
        space_id = default_space(conn)
    if count(conn, space_id) >= MAX_COLLECTIONS:
        raise ValueError(full_message())
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM collections").fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO collections (name, origin, position, parent_id, space_id) VALUES (?, ?, ?, ?, ?)",
        (name, origin, position, int(parent["id"]) if parent else None, space_id),
    )
    return int(cursor.lastrowid or 0)


def exists(conn: sqlite3.Connection, collection_id: int) -> bool:
    return conn.execute("SELECT 1 FROM collections WHERE id = ?", (collection_id,)).fetchone() is not None


def create(conn: sqlite3.Connection, name: str, origin: str = "mine", parent_id: int | None = None,
           space_id: int | None = None) -> int:
    if find(conn, name):
        raise ValueError(f"There's already a collection called “{clean_name(name)}”.")
    if parent_id is not None:
        if not exists(conn, parent_id):
            raise ValueError("That collection doesn't exist any more.")
        if depth(conn, parent_id) >= MAX_DEPTH:
            raise ValueError(f"Collections can go {MAX_DEPTH} levels deep at most.")
    return ensure(conn, name, origin, parent_id, space_id)


def rename(conn: sqlite3.Connection, collection_id: int, name: str) -> None:
    name = clean_name(name)
    if not name:
        raise ValueError("A collection needs a name.")
    other = find(conn, name)
    if other and int(other["id"]) != collection_id:
        raise ValueError(f"There's already a collection called “{name}”. Use Merge to join the two.")
    # Renaming an AI idea makes it the user's own.
    conn.execute(
        "UPDATE collections SET name = ?, origin = CASE origin WHEN 'ai' THEN 'mine' ELSE origin END "
        "WHERE id = ?",
        (name, collection_id),
    )


def merge(conn: sqlite3.Connection, source_id: int, target_id: int) -> None:
    """Move every save from one collection into another, then delete the
    first. Collections inside the first one move up a level."""
    if source_id == target_id:
        raise ValueError("Pick a different collection to merge into.")
    conn.execute(
        "INSERT OR IGNORE INTO item_collections (item_id, collection_id, source, confidence) "
        "SELECT item_id, ?, source, confidence FROM item_collections WHERE collection_id = ?",
        (target_id, source_id),
    )
    conn.execute("UPDATE platform_links SET collection_id = ? WHERE collection_id = ?", (target_id, source_id))
    conn.execute("UPDATE platform_import_destinations SET collection_id = ? WHERE collection_id = ?", (target_id, source_id))
    delete(conn, source_id)


def delete(conn: sqlite3.Connection, collection_id: int) -> None:
    """Delete a collection. The collections inside it move up one level; its
    saves stay in the app."""
    row = conn.execute("SELECT parent_id FROM collections WHERE id = ?", (collection_id,)).fetchone()
    if row is None:
        return
    conn.execute("UPDATE collections SET parent_id = ? WHERE parent_id = ?", (row["parent_id"], collection_id))
    conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))


# The small pictures a collection's folder can carry (none: a plain folder).
ICONS = ("star", "heart", "book", "film", "music", "food", "plane", "home", "cart", "game", "fitness", "code", "idea", "camera", "work", "money", "leaf", "pin")


CUSTOM_ICON = "custom:"  # then a number that changes with every upload, so the window reloads it


def set_custom_icon(conn: sqlite3.Connection, collection_id: int, stamp: int) -> None:
    """Mark the collection as showing the user's own picture."""
    conn.execute("UPDATE collections SET icon = ? WHERE id = ?", (f"{CUSTOM_ICON}{stamp}", collection_id))


def update(conn: sqlite3.Connection, collection_id: int, **fields: Any) -> None:
    """Change description, ai_allowed, color or icon."""
    fields.pop("collapsed", None)  # folders are gone; ignored if an old window sends it
    allowed = {"description", "ai_allowed", "color", "icon"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Can't change {', '.join(sorted(unknown))}.")
    if "color" in fields and fields["color"] not in (None, *COLORS):
        raise ValueError("Unknown colour.")
    if "icon" in fields:
        fields["icon"] = fields["icon"] or None  # "" or null: a plain folder again
        if fields["icon"] not in (None, *ICONS):
            raise ValueError("Unknown icon.")  # an own picture is set with set_custom_icon
    if "description" in fields and fields["description"] is not None:
        fields["description"] = " ".join(str(fields["description"]).split())[:300] or None
    if "ai_allowed" in fields:
        fields["ai_allowed"] = int(bool(fields["ai_allowed"]))
    if fields:
        sets = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(f"UPDATE collections SET {sets} WHERE id = ?", (*fields.values(), collection_id))


def depth(conn: sqlite3.Connection, collection_id: int) -> int:
    """1 for a collection at the top of its space, 2 inside one, and so on."""
    level = 0
    current: int | None = collection_id
    seen: set[int] = set()
    while current is not None and current not in seen:
        seen.add(current)
        level += 1
        row = conn.execute("SELECT parent_id FROM collections WHERE id = ?", (current,)).fetchone()
        current = row["parent_id"] if row else None
    return level


def _subtree_height(conn: sqlite3.Connection, collection_id: int) -> int:
    """How many levels this collection and everything inside it take up."""
    children = [int(r["id"]) for r in conn.execute("SELECT id FROM collections WHERE parent_id = ?", (collection_id,))]
    return 1 + max((_subtree_height(conn, child) for child in children), default=0)


def descendants(conn: sqlite3.Connection, collection_id: int) -> list[int]:
    """This collection and every collection inside it, at any depth."""
    rows = conn.execute(
        """WITH RECURSIVE tree(id) AS (
               SELECT ? UNION SELECT c.id FROM collections c JOIN tree ON c.parent_id = tree.id)
           SELECT id FROM tree""",
        (collection_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def place(conn: sqlite3.Connection, collection_id: int, parent_id: int | None, index: int,
          space_id: int | None = None) -> None:
    """Move a collection inside another one (parent_id), or to the top of a
    space (parent_id None; space_id None = the space it's in), at a position
    among its new neighbours. Everything inside it comes along."""
    row = conn.execute("SELECT space_id FROM collections WHERE id = ?", (collection_id,)).fetchone()
    if row is None:
        raise ValueError("That collection doesn't exist any more.")
    old_space = int(row["space_id"])
    inside = descendants(conn, collection_id)
    if parent_id is not None:
        parent = conn.execute("SELECT space_id FROM collections WHERE id = ?", (parent_id,)).fetchone()
        if parent is None:
            raise ValueError("That collection doesn't exist any more.")
        if parent_id in inside:
            raise ValueError("A collection can't go inside itself.")
        if depth(conn, parent_id) + _subtree_height(conn, collection_id) > MAX_DEPTH:
            raise ValueError(f"Collections can go {MAX_DEPTH} levels deep at most.")
        new_space = int(parent["space_id"])
    else:
        new_space = old_space if space_id is None else space_id
        if not space_exists(conn, new_space):
            raise ValueError("That space doesn't exist any more.")
    if new_space != old_space and count(conn, new_space) + len(inside) > MAX_COLLECTIONS:
        raise ValueError(full_message())
    siblings = [
        int(r["id"])
        for r in conn.execute(
            "SELECT id FROM collections WHERE parent_id IS ? AND space_id = ? AND id != ? ORDER BY position, id",
            (parent_id, new_space, collection_id),
        )
    ]
    siblings.insert(max(0, min(index, len(siblings))), collection_id)
    conn.execute("UPDATE collections SET parent_id = ? WHERE id = ?", (parent_id, collection_id))
    marks = ",".join("?" for _ in inside)
    conn.execute(f"UPDATE collections SET space_id = ? WHERE id IN ({marks})", (new_space, *inside))
    for position, sibling in enumerate(siblings, start=1):
        conn.execute("UPDATE collections SET position = ? WHERE id = ?", (position, sibling))


def list_all(conn: sqlite3.Connection, platform: str | None = None) -> list[dict[str, Any]]:
    """Every collection with its save count (only that platform's saves when
    one is picked), space by space, each one followed by what's inside it.
    `path` is "Outer / Inner / Name"; `total` also counts what's inside."""
    join = "LEFT JOIN items i ON i.id = ic.item_id AND i.deleted_at IS NULL" + (" AND i.platform = ?" if platform else "")
    rows = conn.execute(
        f"""SELECT c.id, c.name, c.origin, c.description, c.position, c.ai_allowed, c.color, c.icon,
                  c.parent_id, c.space_id,
                  COUNT(i.id) AS count,
                  SUM(i.id IS NOT NULL AND i.done = 1) AS done_count,
                  SUM(i.id IS NOT NULL AND ic.source = 'ai') AS ai_count
           FROM collections c LEFT JOIN item_collections ic ON ic.collection_id = c.id {join}
           GROUP BY c.id ORDER BY c.position, c.id""",
        [platform] if platform else [],
    ).fetchall()
    found = [dict(row) for row in rows]
    by_id = {row["id"]: row for row in found}
    by_parent: dict[tuple[int, int | None], list[dict[str, Any]]] = {}
    for row in found:
        row.update(
            ai_allowed=bool(row["ai_allowed"]),
            done_count=int(row["done_count"] or 0),
            ai_count=int(row["ai_count"] or 0),
            collapsed=False,
        )
        parent = by_id.get(row["parent_id"])
        if parent is None or parent["space_id"] != row["space_id"]:
            row["parent_id"] = None  # a lost link: show it at the top of its space
        by_parent.setdefault((row["space_id"], row["parent_id"]), []).append(row)
    ordered: list[dict[str, Any]] = []

    def walk(space_id: int, parent: int | None, path: list[str], level: int) -> int:
        inside = 0
        for row in by_parent.get((space_id, parent), []):
            row["path"] = " / ".join([*path, row["name"]])
            row["depth"] = level
            row["has_children"] = (space_id, row["id"]) in by_parent
            ordered.append(row)
            row["total"] = row["count"] + walk(space_id, row["id"], [*path, row["name"]], level + 1)
            inside += row["total"]
        return inside

    space_ids = [int(r["id"]) for r in conn.execute("SELECT id FROM spaces ORDER BY position, id")]
    for space_id in space_ids + sorted({row["space_id"] for row in found} - set(space_ids)):
        walk(space_id, None, [], 0)
    return ordered


def names(conn: sqlite3.Connection, origins: tuple[str, ...] = ("mine",), ai_only: bool = False) -> list[str]:
    marks = ",".join("?" for _ in origins)
    extra = " AND ai_allowed = 1" if ai_only else ""
    rows = conn.execute(
        f"SELECT name FROM collections WHERE origin IN ({marks}){extra} ORDER BY position, id", origins
    ).fetchall()
    return [str(row["name"]) for row in rows]


def all_names(conn: sqlite3.Connection) -> list[str]:
    return [str(row["name"]) for row in conn.execute("SELECT name FROM collections ORDER BY position, id")]


def ai_choices(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """The collections the AI may file videos into, with the user's note on
    what belongs there (shown to the AI)."""
    linked: dict[int, list[str]] = {}
    for link in conn.execute(
        "SELECT collection_id, platform, name FROM platform_links WHERE collection_id IS NOT NULL ORDER BY id"
    ):
        linked.setdefault(int(link["collection_id"]), []).append(f"{link['platform']} '{link['name']}'")
    space_names = {int(r["id"]): str(r["name"]) for r in conn.execute("SELECT id, name FROM spaces")}
    out = []
    for row in list_all(conn):
        if row["origin"] not in ("mine", "ai", "platform") or not row["ai_allowed"]:
            continue
        description = row["description"] or ""
        if row["id"] in linked:
            # The user's own platform collections that belong here: a strong
            # hint, and the only one TikTok exports give (names, no videos).
            hint = "the user's platform collections " + ", ".join(linked[row["id"]][:8]) + " belong here"
            description = f"{description}; {hint}" if description else hint
        folder = row["path"].rsplit(" / ", 1)[0] if " / " in row["path"] else ""
        if len(space_names) > 1:
            folder = " / ".join(part for part in (space_names.get(row["space_id"], ""), folder) if part)
        out.append({"name": row["name"], "folder": folder, "description": description})
    return out


def links_of(conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.id, c.name, c.origin, c.color, ic.source, ic.confidence
           FROM item_collections ic JOIN collections c ON c.id = ic.collection_id
           WHERE ic.item_id = ? ORDER BY c.position, c.id""",
        (item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_links(
    conn: sqlite3.Connection, item_id: int, links: list[Link], keep_sources: tuple[str, ...] = ("user",),
    new_parent: int | None = None,
) -> None:
    """Swap the item's automatic links for new ones; links from keep_sources
    stay. Links to collections that don't exist are skipped."""
    marks = ",".join("?" for _ in keep_sources)
    where = f" AND source NOT IN ({marks})" if keep_sources else ""
    conn.execute(f"DELETE FROM item_collections WHERE item_id = ?{where}", (item_id, *keep_sources))
    for link in links:
        row = find(conn, link.name)
        if row is None:
            continue
        if count_on(conn, item_id) >= MAX_PER_ITEM:
            break  # the user's own picks come first
        conn.execute(
            "INSERT OR IGNORE INTO item_collections (item_id, collection_id, source, confidence) "
            "VALUES (?, ?, ?, ?)",
            (item_id, int(row["id"]), link.source, link.confidence),
        )


def add_by_user(conn: sqlite3.Connection, item_id: int, collection_id: int) -> None:
    """Raises SaveFull when the save is already in MAX_PER_ITEM collections."""
    if not has_link(conn, item_id, collection_id) and count_on(conn, item_id) >= MAX_PER_ITEM:
        raise SaveFull(save_full_message())
    conn.execute(
        """INSERT INTO item_collections (item_id, collection_id, source) VALUES (?, ?, 'user')
           ON CONFLICT (item_id, collection_id) DO UPDATE SET source = 'user'""",
        (item_id, collection_id),
    )
    _reviewed(conn, item_id)


def add_from_platform(conn: sqlite3.Connection, item_id: int, collection_id: int) -> bool:
    """File a save because of a platform link. Never overrides the user's own
    choice. True if the placement is newly backed by platform routing."""
    if not has_link(conn, item_id, collection_id) and count_on(conn, item_id) >= MAX_PER_ITEM:
        return False
    cursor = conn.execute(
        """INSERT INTO item_collections (item_id, collection_id, source) VALUES (?, ?, 'platform')
           ON CONFLICT (item_id, collection_id) DO UPDATE SET source = 'platform', confidence = NULL
           WHERE item_collections.source IN ('ai', 'rule')""",
        (item_id, collection_id),
    )
    if cursor.rowcount:
        _reviewed(conn, item_id)
    return bool(cursor.rowcount)


def remove(conn: sqlite3.Connection, item_id: int, collection_id: int) -> None:
    conn.execute(
        "DELETE FROM item_collections WHERE item_id = ? AND collection_id = ?", (item_id, collection_id)
    )


def move(conn: sqlite3.Connection, item_id: int, from_id: int | None, to_id: int) -> None:
    """Take the item out of from_id (if given) and put it in to_id."""
    if from_id is not None and from_id != to_id:
        remove(conn, item_id, from_id)
    add_by_user(conn, item_id, to_id)


def _reviewed(conn: sqlite3.Connection, item_id: int) -> None:
    """The user has decided where it goes, so it leaves the inbox."""
    conn.execute("UPDATE items SET needs_review = 0, review_reason = NULL WHERE id = ?", (item_id,))


def names_from_imports(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(platform, collection name) pairs found in earlier imports, e.g.
    TikTok's list of collection names, in order."""
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    rows = conn.execute(
        "SELECT result_json FROM jobs WHERE kind = 'import' AND status = 'done' ORDER BY id"
    ).fetchall()
    for row in rows:
        try:
            result = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            continue
        for platform in result.get("platforms", []):
            for name in platform.get("collections", []):
                cleaned = clean_name(str(name))
                key = (str(platform.get("platform") or ""), cleaned.lower())
                if cleaned and key not in seen:
                    seen.add(key)
                    found.append((key[0], cleaned))
    return found


def seed_once(db: Database, settings: SettingsRepo) -> None:
    """The first time collections are used, start the user's list with a few
    broad topics. Only ever once, so deleting collections later doesn't bring
    them back. Platform collection names (TikTok can have dozens of small
    ones) are linked to these on the Collections screen instead."""
    if settings.get(SEEDED_KEY, False):
        return
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM collections LIMIT 1").fetchone():
            for name in STARTER_COLLECTIONS:
                ensure(conn, name, "mine")
    settings.set(SEEDED_KEY, True)  # after the block above has saved
