"""Routes for the Library grid, the overview counts, an item's checklist,
the Unsave checklist, the platform picker and the look of the app.

Everything here except the look follows the platform picker (scope.py)."""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.ai.sorting import collections as collections_repo
from app.ai.sorting import tags as tags_repo
from app.ai.sorting.settings import KIND_LABELS, KINDS
from app.api.sorting import CARD_SQL, cards_from_rows, one_card
from app.importers import PLATFORM_NAMES
from app.library import progress, scope, unsave_export
from app.search.keyword import fts_query
from app.services import AppServices, services

router = APIRouter(prefix="/api")

MAX_PAGE = 120

Status = Literal["all", "processed", "waiting", "failed"]
Progress = Literal["any", "not_started", "started", "done"]
Sort = Literal[
    "newest", "oldest", "title", "title_desc", "posted_newest", "posted_oldest", "creator",
    "longest", "shortest", "recently_sorted", "most_steps",
]

STATUS_SQL: dict[str, str] = {
    "all": "1",
    "processed": "i.status = 'processed'",
    "waiting": "i.status IN ('imported', 'enriched')",
    "failed": "i.status = 'failed'",
}
PROGRESS_SQL: dict[str, str] = {
    "any": "1",
    "not_started": "i.started_at IS NULL AND i.done = 0",
    "started": "i.started_at IS NOT NULL AND i.done = 0",
    "done": "i.done = 1",
}
SORT_SQL: dict[str, str] = {
    "newest": "i.saved_at DESC, i.id DESC",
    "oldest": "i.saved_at ASC, i.id ASC",
    # Items without a title yet go last.
    "title": "coalesce(a.title, i.title, i.description, i.caption) IS NULL, "
             "lower(coalesce(a.title, i.title, i.description, i.caption)), i.id",
    "title_desc": "coalesce(a.title, i.title, i.description, i.caption) IS NULL, "
                  "lower(coalesce(a.title, i.title, i.description, i.caption)) DESC, i.id",
    # Videos whose posting date or length isn't known yet go last.
    "posted_newest": "i.posted_at IS NULL, i.posted_at DESC, i.id DESC",
    "posted_oldest": "i.posted_at IS NULL, i.posted_at ASC, i.id ASC",
    "creator": "i.author IS NULL, lower(i.author), i.saved_at DESC",
    "longest": "i.duration_s IS NULL, i.duration_s DESC, i.id DESC",
    "shortest": "i.duration_s IS NULL, i.duration_s ASC, i.id ASC",
    "recently_sorted": "i.sorted_at IS NULL, i.sorted_at DESC, i.id DESC",
    "most_steps": "json_array_length(coalesce(a.steps_json, '[]')) DESC, i.saved_at DESC",
}


# ---------- library grid ----------


@router.get("/library/items")
def library_items(
    status: Status = "all",
    progress_filter: Progress = Query("any", alias="progress"),
    platform: str | None = None,
    kind: str | None = None,
    collection_id: int | None = None,
    include_sub: bool = True,  # a folder also shows what's in the collections inside it
    in_collection: Literal["any", "none"] = "any",  # none: saves that aren't in any collection
    tag: str | None = None,
    tags: str | None = None,  # several tags, comma separated: saves with all of them
    creator: str | None = None,
    q: str | None = None,  # words in the title, caption, transcript, notes or tags
    sort: Sort = "newest",
    # The Archive: "deleted" = saves you deleted, "unsaved" = ones you've unsaved on the platform,
    # "gone" = ones taken down on the platform (Deleted TikToks).
    archive: Literal["none", "deleted", "unsaved", "gone"] = "none",
    offset: int = 0,
    limit: int = 60,
    svc: AppServices = Depends(services),
) -> dict[str, Any]:
    where = [STATUS_SQL[status], PROGRESS_SQL[progress_filter]]
    params: list[Any] = []
    if archive == "deleted":
        where.append("i.deleted_at IS NOT NULL")
    elif archive == "gone":
        where.append("i.deleted_at IS NULL AND i.gone_at IS NOT NULL")
    else:
        where.append("i.deleted_at IS NULL AND i.gone_at IS NULL")
    if archive == "unsaved":
        where.append("i.unsaved = 1")
    if not platform:
        scoped, scoped_params = scope.where(scope.current(svc.settings), deleted=None)
        where.append(scoped)
        params.extend(scoped_params)
    wanted_tags = [tags_repo.clean_tag(t) for t in ([tag] if tag else []) + (tags or "").split(",")]
    for name in dict.fromkeys(t for t in wanted_tags if t):
        where.append(
            "EXISTS (SELECT 1 FROM item_tags it JOIN tags t ON t.id = it.tag_id WHERE it.item_id = i.id AND t.name = ?)"
        )
        params.append(name)
    match = fts_query(q or "")
    if match:
        where.append("i.id IN (SELECT rowid FROM search_fts WHERE search_fts MATCH ?)")
        params.append(match)
    if in_collection == "none":
        where.append("NOT EXISTS (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id)")
    if creator:
        where.append("lower(ltrim(i.author, '@')) = ?")
        params.append(creator.lstrip("@").lower())
    if platform:
        where.append("i.platform = ?")
        params.append(platform)
    if kind:
        where.append("a.kind = ?")
        params.append(kind)
    limit = max(1, min(limit, MAX_PAGE))
    offset = max(0, offset)
    with svc.db.connect() as conn:
        if collection_id is not None:
            ids = collections_repo.descendants(conn, collection_id) if include_sub else [collection_id]
            marks = ",".join("?" for _ in ids)
            where.append(
                f"EXISTS (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id AND ic.collection_id IN ({marks}))"
            )
            params.extend(ids)
        clause = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) FROM items i LEFT JOIN ai_results a ON a.item_id = i.id WHERE {clause}", params
        ).fetchone()[0]
        order = {"deleted": "i.deleted_at DESC, i.id DESC", "unsaved": "i.unsaved_at DESC, i.id DESC",
                 "gone": "i.gone_at DESC, i.id DESC"}.get(
            archive if sort == "newest" else "", SORT_SQL[sort]
        )
        rows = conn.execute(
            f"{CARD_SQL} WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?", [*params, limit, offset]
        ).fetchall()
        return {"total": int(total), "offset": offset, "items": cards_from_rows(conn, rows)}


@router.get("/library/filters")
def library_filters(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """What the filter menus offer, with how many items each choice has
    (for the platform chosen in the picker)."""
    chosen = scope.current(svc.settings)
    scoped, params = scope.where(chosen)
    with svc.db.connect() as conn:
        platforms = conn.execute(
            f"SELECT platform, COUNT(*) AS n FROM items i WHERE {scoped} GROUP BY platform ORDER BY n DESC", params
        ).fetchall()
        kinds = dict(conn.execute(
            f"SELECT a.kind, COUNT(*) FROM ai_results a JOIN items i ON i.id = a.item_id "
            f"WHERE a.kind IS NOT NULL AND {scoped} GROUP BY a.kind",
            params,
        ).fetchall())
        cols = collections_repo.list_all(conn, chosen)
        tag_rows = [row for row in tags_repo.list_all(conn, chosen) if row["count"] > 0]
        no_collection = conn.execute(
            f"SELECT COUNT(*) FROM items i WHERE {scoped} AND "
            "NOT EXISTS (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id)",
            params,
        ).fetchone()[0]
        creators = conn.execute(
            f"""SELECT ltrim(i.author, '@') AS name, COUNT(*) AS n FROM items i
                WHERE i.author IS NOT NULL AND i.author <> '' AND {scoped}
                GROUP BY lower(ltrim(i.author, '@')) HAVING n > 1 ORDER BY n DESC LIMIT 50""",
            params,
        ).fetchall()
    return {
        "platforms": [
            {"id": row["platform"], "label": PLATFORM_NAMES.get(row["platform"], row["platform"]), "count": row["n"]}
            for row in platforms
        ],
        "kinds": [{"id": kind, "label": KIND_LABELS[kind], "count": int(kinds.get(kind, 0))} for kind in KINDS],
        "collections": [
            {"id": row["id"], "label": row["name"], "count": row["count"], "depth": row["depth"]} for row in cols
        ],
        "tags": [{"id": row["name"], "label": row["name"], "count": row["count"]} for row in tag_rows],
        "creators": [{"id": row["name"], "label": f"@{row['name']}", "count": row["n"]} for row in creators],
        "no_collection": int(no_collection),
    }


# ---------- overview counts (the sidebar badges) ----------


def _overview_counts(conn: sqlite3.Connection, platform: str | None = None) -> dict[str, int]:
    scoped, params = scope.where(platform, "items")
    row = conn.execute(
        f"""SELECT COUNT(*) AS total,
                  SUM(status = 'processed') AS processed,
                  SUM(status IN ('imported', 'enriched')) AS waiting,
                  SUM(status = 'enriched') AS ready_for_notes,
                  SUM(status = 'failed') AS failed,
                  SUM(started_at IS NOT NULL AND done = 0) AS in_progress,
                  SUM(done = 1) AS done,
                  SUM(unsaved = 1) AS unsaved
           FROM items WHERE {scoped}""",
        params,
    ).fetchone()
    counts = {key: int(row[key] or 0) for key in row.keys()}
    # The Unsave list also has the saves you deleted.
    unsave_scope, unsave_params = scope.where(platform, "items", deleted=None)
    counts["to_unsave"] = int(conn.execute(
        f"SELECT COUNT(*) FROM items WHERE safe_to_unsave = 1 AND unsaved = 0 AND gone_at IS NULL AND {unsave_scope}",
        unsave_params,
    ).fetchone()[0])
    # Plans are the user's own lists: open ones (not finished).
    counts["open_plans"] = int(conn.execute("SELECT COUNT(*) FROM plans WHERE done_at IS NULL").fetchone()[0])
    return counts


@router.get("/overview")
def overview(svc: AppServices = Depends(services)) -> dict[str, Any]:
    chosen = scope.current(svc.settings)
    scoped, params = scope.where(chosen)
    with svc.db.connect() as conn:
        counts = _overview_counts(conn, chosen)
        recent = conn.execute(
            f"{CARD_SQL} WHERE i.status = 'processed' AND {scoped} "
            "ORDER BY coalesce(i.processed_at, i.saved_at) DESC, i.id DESC LIMIT 8",
            params,
        ).fetchall()
        return {
            "counts": counts,
            "recent": cards_from_rows(conn, recent),
            "plans": [],
        }


# ---------- the platform picker ----------


class ScopeBody(BaseModel):
    platform: str | None = None  # None = All


@router.get("/scope")
def get_scope(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        found = scope.choices(conn)
        total = sum(choice["count"] for choice in found)
    return {"platform": scope.current(svc.settings), "platforms": found, "total": total}


@router.put("/scope")
def put_scope(body: ScopeBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        scope.choose(svc.settings, body.platform)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return get_scope(svc)


# ---------- one item: checklist, done, unsaved ----------


class TickBody(BaseModel):
    done: bool


@router.put("/items/{item_id}/steps/{index}")
def tick(item_id: int, index: int, body: TickBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        try:
            progress.tick_step(conn, item_id, index, body.done)
        except IndexError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return one_card(conn, item_id)


class ItemPatch(BaseModel):
    done: bool | None = None
    safe_to_unsave: bool | None = None
    unsaved: bool | None = None
    deleted: bool | None = None  # True: to the Archive; False: put it back


@router.patch("/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        if body.done is not None:
            progress.set_done(conn, item_id, body.done)
        if body.safe_to_unsave is not None:
            progress.set_safe(conn, item_id, body.safe_to_unsave)
        if body.unsaved is not None:
            progress.set_unsaved(conn, item_id, body.unsaved)
        if body.deleted is not None:
            progress.set_deleted(conn, item_id, body.deleted)
        return one_card(conn, item_id)


def remove_files(svc: AppServices, item_id: int, names: list[str]) -> None:
    """Remove a purged save's picture and any sound file left from a download."""
    folder = svc.paths.thumbnails.resolve()
    for name in names:
        path = (folder / name).resolve()
        if path.is_relative_to(folder):
            path.unlink(missing_ok=True)
    for leftover in [*svc.paths.audio.glob(f"{item_id}.*"), *svc.paths.thumbnails.glob(f"{item_id}-f*.jpg")]:
        leftover.unlink(missing_ok=True)


@router.delete("/items/{item_id}")
def purge_item(item_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Delete a save for good. Only from the Archive: it has to be deleted first."""
    with svc.db.connect() as conn:
        card = one_card(conn, item_id)
        if not card["deleted"]:
            raise HTTPException(status_code=400, detail="Delete it first; then it can be deleted for good from the Archive.")
        names = progress.purge(conn, item_id)
    remove_files(svc, item_id, names)
    return {"purged": 1}


@router.get("/archive")
def archive_counts(svc: AppServices = Depends(services)) -> dict[str, int]:
    """How many saves are in each part of the Archive (for the chosen platform)."""
    chosen = scope.current(svc.settings)
    platform_sql, params = scope.where(chosen, "items", deleted=None)
    with svc.db.connect() as conn:
        row = conn.execute(
            f"""SELECT SUM(deleted_at IS NOT NULL) AS deleted,
                       SUM(deleted_at IS NULL AND gone_at IS NULL AND unsaved = 1) AS unsaved,
                       SUM(deleted_at IS NULL AND gone_at IS NOT NULL) AS gone
                FROM items WHERE {platform_sql}""",
            params,
        ).fetchone()
    return {key: int(row[key] or 0) for key in ("deleted", "unsaved", "gone")}


@router.post("/items/{item_id}/restart")
def restart_item(item_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        progress.restart(conn, item_id)
        return one_card(conn, item_id)


# ---------- unsave ----------


def _unsave_cards(conn: sqlite3.Connection, platform: str | None = None) -> list[dict[str, Any]]:
    """Every save whose notes are in, and every save you deleted. Not the
    ones taken down: there's nothing left on the platform to unsave."""
    scoped, params = scope.where(platform, deleted=None)
    rows = conn.execute(
        f"{CARD_SQL} WHERE i.safe_to_unsave = 1 AND i.gone_at IS NULL AND {scoped} ORDER BY i.unsaved, i.platform, i.saved_at DESC, i.id DESC",
        params,
    ).fetchall()
    return cards_from_rows(conn, rows)


@router.get("/unsave")
def unsave_list(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        cards = _unsave_cards(conn, scope.current(svc.settings))
    return {
        "items": cards,
        "left": sum(1 for card in cards if not card["unsaved"]),
    }


@router.get("/unsave/export.csv")
def unsave_csv(svc: AppServices = Depends(services)) -> Response:
    """The same list as a CSV download (for a normal browser)."""
    with svc.db.connect() as conn:
        text = unsave_export.to_csv(_unsave_cards(conn, scope.current(svc.settings)))
    return Response(
        content=("﻿" + text).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="saves-to-unsave.csv"'},
    )


@router.post("/unsave/export")
def unsave_export_file(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Save the list as a CSV file in the user's Downloads folder."""
    with svc.db.connect() as conn:
        cards = _unsave_cards(conn, scope.current(svc.settings))
    if not cards:
        raise HTTPException(status_code=400, detail="Nothing is safe to unsave yet, so there's nothing to export.")
    path = unsave_export.save_csv(unsave_export.to_csv(cards), unsave_export.downloads_folder())
    return {"path": str(path), "count": len(cards)}


@router.post("/unsave/open-folder")
def open_downloads() -> dict[str, bool]:
    """Show the Downloads folder in File Explorer (Windows only)."""
    starter = getattr(os, "startfile", None)
    if starter is None:
        return {"opened": False}
    starter(str(unsave_export.downloads_folder()))
    return {"opened": True}


def open_in_browser(url: str) -> bool:
    """Open a web page in the user's normal browser. Tests replace this."""
    import webbrowser

    return webbrowser.open(url)


@router.post("/items/{item_id}/open")
def open_item(item_id: int, svc: AppServices = Depends(services)) -> dict[str, bool]:
    """Open a save's own page (on TikTok, YouTube, ...) in the user's browser,
    so they can unsave it there themselves. The app itself never logs in to or
    changes anything on the platform."""
    with svc.db.connect() as conn:
        row = conn.execute("SELECT url FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="That save doesn't exist.")
    url = str(row["url"])
    if not url.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="This save has no web link to open.")
    return {"opened": bool(open_in_browser(url))}


# ---------- look of the app ----------

UI_KEY = "ui"
LOOK_VERSION = 2


class UiSettings(BaseModel):
    """How the app looks, chosen in Settings -> Appearance."""

    theme: Literal["system", "light", "dark"] = "system"
    # The highlight colour of buttons, links and the selected page.
    # "default" has no colour of its own: dark in light mode, light in dark mode.
    accent: Literal["default", "violet", "indigo", "blue", "teal", "emerald", "rose", "amber"] = "default"
    # 2: the Default accent exists. Looks saved before that move to it once.
    look_version: int = LOOK_VERSION
    text_size: Literal["small", "normal", "large"] = "normal"
    # The screen the app opens on.
    start_page: Literal["library", "collections", "tags", "plans", "chat", "unsave"] = "library"
    # Used to greet the user ("Hi, Sam"). Empty: no name.
    name: str = Field(default="", max_length=40)
    compact_sidebar: bool = False
    # The sidebar: the order of its pages (drag them), the pages hidden from
    # it, and whether it lists the collections tree and the top tags.
    nav_order: list[str] = Field(default_factory=list, max_length=30)
    nav_hidden: list[str] = Field(default_factory=list, max_length=30)
    sidebar_collections: bool = True
    sidebar_tags: bool = True
    sidebar_folded: list[str] = Field(default_factory=list, max_length=10)  # "collections", "tags"
    # The Library grid: how big the pictures are.
    card_size: Literal["small", "medium", "large"] = "medium"
    # Tips and suggestions the user closed (their ids), so they stay closed.
    dismissed_tips: list[str] = Field(default_factory=list, max_length=200)
    # The quick buttons on a card when the mouse is over it.
    card_actions: bool = True
    # The first-run setup (name, look, start page) was finished or skipped.
    welcomed: bool = False
    hide_tips: bool = False  # long-time users: no tips, blurbs or descriptions

    @field_validator("start_page", mode="before")
    @classmethod
    def _no_home(cls, value: object) -> object:
        return "library" if value == "home" else value  # Home was removed in 0.3


@router.get("/ui")
def get_ui(svc: AppServices = Depends(services)) -> UiSettings:
    saved = dict(svc.settings.get(UI_KEY, {}) or {})
    if saved and int(saved.get("look_version") or 1) < LOOK_VERSION:
        # The Default accent arrived: start on it once, keep every other choice.
        saved |= {"accent": "default", "look_version": LOOK_VERSION}
        svc.settings.set(UI_KEY, saved)
    try:
        return UiSettings.model_validate(saved)
    except ValueError:
        return UiSettings()


@router.put("/ui")
def put_ui(body: UiSettings, svc: AppServices = Depends(services)) -> UiSettings:
    svc.settings.set(UI_KEY, body.model_dump())
    return body
