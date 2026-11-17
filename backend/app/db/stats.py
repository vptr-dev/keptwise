"""Numbers about the database, for the developer page."""

from __future__ import annotations

from typing import Any

from app.db.connection import Database
from app.db.migrations import schema_version

COUNTED_TABLES = (
    "items",
    "transcripts",
    "ai_results",
    "collections",
    "embeddings",
    "jobs",
    "settings",
)


def database_stats(db: Database) -> dict[str, Any]:
    with db.connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in COUNTED_TABLES
        }
        by_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM items GROUP BY status"
            )
        }
        version = schema_version(conn)
    return {
        "path": str(db.path),
        "size_bytes": db.size_bytes(),
        "schema_version": version,
        "tables": counts,
        "items_by_status": by_status,
    }
