"""Reading and writing saved items (posts and videos).

All functions take an open connection, so callers can group several
changes into one transaction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

# Columns that callers may change with update_item().
UPDATABLE = {
    "author",
    "caption",
    "title",
    "description",
    "thumbnail_url",
    "thumbnail_path",
    "duration_s",
    "saved_at",
    "platform_collection",
    "external_id",
    "status",
    "error",
    "done",
    "safe_to_unsave",
    "unsaved",
    "started_at",
    "done_at",
    "unsaved_at",
    "posted_at",
    "enriched_at",
    "enrich_seconds",
    "needs_review",
    "review_reason",
    "processed_at",
    "sorted_at",
    "deleted_at",
    "gone_at",
}

# Item statuses, in the order an item normally moves through them.
STATUSES = ("imported", "enriched", "processed", "failed")


@dataclass
class NewItem:
    """One saved post or video, as read from an export file."""

    platform: str
    url: str
    author: str | None = None
    caption: str | None = None
    saved_at: str | None = None
    platform_collection: str | None = None
    external_id: str | None = None
    thumbnail_url: str | None = None


def upsert_item(conn: sqlite3.Connection, item: NewItem) -> tuple[int, bool]:
    """Add an item, or fill in blanks on the existing one with the same URL.

    Returns (item id, True if it was new). Importing the same export twice
    therefore never creates duplicates.
    """
    existing = conn.execute(
        "SELECT id FROM items WHERE platform = ? AND url = ?",
        (item.platform, item.url),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE items SET
                 author = COALESCE(author, ?),
                 caption = COALESCE(caption, ?),
                 saved_at = COALESCE(saved_at, ?),
                 platform_collection = COALESCE(platform_collection, ?),
                 external_id = COALESCE(external_id, ?),
                 thumbnail_url = COALESCE(thumbnail_url, ?)
               WHERE id = ?""",
            (
                item.author,
                item.caption,
                item.saved_at,
                item.platform_collection,
                item.external_id,
                item.thumbnail_url,
                existing["id"],
            ),
        )
        return int(existing["id"]), False
    cursor = conn.execute(
        """INSERT INTO items (platform, url, author, caption, saved_at,
                              platform_collection, external_id, thumbnail_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.platform,
            item.url,
            item.author,
            item.caption,
            item.saved_at,
            item.platform_collection,
            item.external_id,
            item.thumbnail_url,
        ),
    )
    return int(cursor.lastrowid or 0), True


def update_item(conn: sqlite3.Connection, item_id: int, **fields: Any) -> None:
    """Change some columns of one item. Unknown column names are refused."""
    unknown = set(fields) - UPDATABLE
    if unknown:
        raise ValueError(f"Can't update these item fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(
        f"UPDATE items SET {assignments}, "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
        (*fields.values(), item_id),
    )


def get_item_row(conn: sqlite3.Connection, item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def item_ids_with_status(conn: sqlite3.Connection, *statuses: str) -> list[int]:
    marks = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"SELECT id FROM items WHERE status IN ({marks}) AND deleted_at IS NULL ORDER BY id", statuses
    ).fetchall()
    return [int(row["id"]) for row in rows]


def save_transcript(
    conn: sqlite3.Connection,
    item_id: int,
    text: str,
    language: str | None,
    source: str,
) -> None:
    conn.execute(
        """INSERT INTO transcripts (item_id, text, language, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (item_id) DO UPDATE SET
             text = excluded.text, language = excluded.language,
             source = excluded.source""",
        (item_id, text, language, source),
    )


def get_transcript(conn: sqlite3.Connection, item_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT text, language, source FROM transcripts WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


def decode_json_list(value: str | None) -> list[Any]:
    """Columns like tags hold JSON lists; turn them back into Python lists."""
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []
