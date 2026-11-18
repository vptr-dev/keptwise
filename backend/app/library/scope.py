"""Which platform the user is looking at: All, or just TikTok, YouTube, ...

The picker at the top left of the window sets it, and the Library,
Collections, Tags, Plans, Unsave, search and the AI Assistant all show only
that platform's saves. Import, Transcripts and Settings always cover every
platform. Stored as a setting, so it is the same on every screen and after a
restart.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.db.settings_repo import SettingsRepo
from app.importers import PLATFORM_NAMES

KEY = "scope.platform"


def current(settings: SettingsRepo) -> str | None:
    """The chosen platform id, or None for All."""
    value = settings.get(KEY, None)
    return str(value) if value in PLATFORM_NAMES else None


def choose(settings: SettingsRepo, platform: str | None) -> None:
    if platform and platform not in PLATFORM_NAMES:
        raise ValueError("Unknown platform.")
    settings.set(KEY, platform or None)


def where(platform: str | None, alias: str = "i", deleted: bool | None = False) -> tuple[str, list[Any]]:
    """An SQL condition for the saves a list shows: the chosen platform's
    (every platform when All), and not the deleted ones or the ones taken
    down on the platform (deleted=True: only the deleted, for the Archive;
    None: any)."""
    parts = []
    if deleted is not None:
        parts.append(f"{alias}.deleted_at IS {'NOT ' if deleted else ''}NULL")
    if deleted is False:
        parts.append(f"{alias}.gone_at IS NULL")  # taken down: only in the Archive
    if platform:
        parts.append(f"{alias}.platform = ?")
    return " AND ".join(parts) or "1", [platform] if platform else []


def choices(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every platform with saves, most saves first."""
    rows = conn.execute(
        "SELECT platform, COUNT(*) AS n FROM items WHERE deleted_at IS NULL GROUP BY platform ORDER BY n DESC"
    ).fetchall()
    return [
        {"id": row["platform"], "label": PLATFORM_NAMES.get(row["platform"], row["platform"]), "count": int(row["n"])}
        for row in rows
    ]
