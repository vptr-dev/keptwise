"""The "import" background job: read an uploaded export and save its items.

The window first copies the dropped files into
%APPDATA%\\Keptwise\\imports\\<upload id>\\ (see app/api/imports.py),
then starts this job. When the import finishes, that copy is deleted.
If it's cancelled or fails, the copy stays so Resume can try again; copies
older than a day are removed when the app starts.
"""

from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from app.ai.sorting import platform_links
from app.db.connection import Database
from app.db.items_repo import upsert_item
from app.importers import PLATFORM_NAMES, parse_export
from app.importers.source import ExportSource
from app.jobs.runner import Handler, JobContext

# Items saved per database transaction (Cancel works between batches).
BATCH = 200
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
NOTHING_FOUND = (
    "Couldn't find saved items from TikTok, YouTube, Instagram or Facebook in "
    "these files. Drop the export zip itself (or its unzipped folder), and "
    "check it was made in JSON format."
)
FILES_GONE = "The copied export files are gone. Please drag the export in again."

# Two imports at once could both add the same new link; take turns instead.
_one_at_a_time = threading.Lock()


def upload_folder(imports_dir: Path, upload_id: str) -> Path:
    """The folder of one upload. Refuses ids that could point elsewhere."""
    if not UPLOAD_ID.match(upload_id):
        raise ValueError("That isn't a valid upload id.")
    return imports_dir / upload_id


def make_import_handler(db: Database, imports_dir: Path) -> Handler:
    def run_import(ctx: JobContext) -> dict[str, Any]:
        folder = upload_folder(imports_dir, str(ctx.params.get("upload_id", "")))
        if not folder.is_dir():
            raise RuntimeError(FILES_GONE)
        ctx.progress(0, 0, "Reading the export files…")
        with _one_at_a_time:
            summary = import_folder(ctx, db, folder)
        shutil.rmtree(folder, ignore_errors=True)
        return summary

    return run_import


def import_folder(ctx: JobContext, db: Database, folder: Path) -> dict[str, Any]:
    with ExportSource.open(folder) as source:
        results = parse_export(source)
    if not results:
        raise RuntimeError(NOTHING_FOUND)

    total = sum(len(result.items) for result in results)
    done = 0
    platforms: list[dict[str, Any]] = []
    with db.connect() as conn:
        removed = {(row["platform"], row["url"]) for row in conn.execute("SELECT platform, url FROM removed_links")}
    for result in results:
        new = 0
        skipped = sum((item.platform, item.url) in removed for item in result.items)
        items = result.items
        for start in range(0, len(items), BATCH):
            ctx.check()
            with db.connect() as conn:
                for item in items[start : start + BATCH]:
                    if (item.platform, item.url) in removed:
                        continue  # deleted for good by the user: stays gone
                    _, is_new = upsert_item(conn, item)
                    if is_new:
                        new += 1
            done += len(items[start : start + BATCH])
            ctx.progress(done, total, f"Saved {done:,} of {total:,}")
        platforms.append(
            {
                "platform": result.platform,
                "name": PLATFORM_NAMES[result.platform],
                "found": len(items),
                "new": new,
                "already_had": len(items) - new - skipped,
                "deleted_before": skipped,
                "collections": result.collections,
                "notes": result.notes,
            }
        )

    # Saves from platform collections the user linked (auto) get filed.
    with db.connect() as conn:
        platform_links.apply_all_auto(conn)
    new_total = sum(platform["new"] for platform in platforms)
    gone_total = sum(platform["deleted_before"] for platform in platforms)
    return {
        "message": _message(platforms, total - gone_total, new_total)
        + (f" {gone_total:,} you deleted for good stay deleted." if gone_total else ""),
        "found": total,
        "new": new_total,
        "already_had": total - new_total,
        "platforms": platforms,
    }


def _message(platforms: list[dict[str, Any]], total: int, new_total: int) -> str:
    # "TikTok", "TikTok and YouTube", "TikTok, YouTube and Instagram"
    all_names = [platform["name"] for platform in platforms]
    names = " and ".join(filter(None, [", ".join(all_names[:-1]), all_names[-1]]))
    if total == 0:
        return f"Found no saved items in this {names} export."
    if new_total == 0:
        return f"Nothing new: all {total:,} saves from {names} were already in your library."
    saves = "save" if new_total == 1 else "saves"
    message = f"Imported {new_total:,} new {saves} from {names}."
    if total > new_total:
        message += f" {total - new_total:,} were already in your library."
    return message


def remove_old_uploads(imports_dir: Path, max_age_hours: float = 24) -> None:
    """Delete leftover copies of exports (privacy: don't keep them around)."""
    if not imports_dir.is_dir():
        return
    cutoff = time.time() - max_age_hours * 3600
    for folder in imports_dir.iterdir():
        try:
            if folder.is_dir() and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            continue  # in use or already gone; try again next start
