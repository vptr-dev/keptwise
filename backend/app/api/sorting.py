"""Routes for AI notes and sorting: settings, collections, moving items,
Unsorted (saves in no collection, with the AI's suggestion to accept), the
AI's tag suggestions, clearing what the AI did, and starting the notes /
re-sort jobs."""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.ai.base import AIError, Provider
from app.ai.sorting import collections, platform_links, tags
from app.ai.sorting.job import CLOUD_BATCH_LIMIT, now_iso
from app.ai.sorting.settings import DEFAULT_KIND_STEPS, KIND_LABELS, KINDS, SortingSettings, load, save, update
from app.db.items_repo import decode_json_list
from app.importers import PLATFORM_NAMES
from app.library import scope
from app.services import AppServices, services

router = APIRouter(prefix="/api")

PAGE_LIMIT = 200


# ---------- settings ----------


@router.get("/sorting/settings")
def get_settings(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _settings_response(load(svc.settings).model_dump())


def _settings_response(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "settings": settings,
        "kinds": [{"id": kind, "label": KIND_LABELS[kind], "default": DEFAULT_KIND_STEPS[kind]} for kind in KINDS],
    }


@router.put("/sorting/settings")
def put_settings(body: SortingSettings, svc: AppServices = Depends(services)) -> dict[str, Any]:
    save(svc.settings, body)
    return _settings_response(body.model_dump())


@router.patch("/sorting/settings")
def patch_settings(changes: dict[str, Any], svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        return _settings_response(update(svc.settings, changes))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Those sorting settings are invalid.") from error


# ---------- collections ----------


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class NewCollection(NameBody):
    parent_id: int | None = None  # make it inside this collection
    space_id: int | None = None  # or at the top of this space (None = the first space)


class CollectionPatch(BaseModel):
    """Any of these; leave out what doesn't change."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    ai_allowed: bool | None = None
    color: str | None = None
    clear_color: bool = False
    icon: str | None = None  # a name from collections.ICONS; "" or null: a plain folder
    collapsed: bool | None = None


class PlaceBody(BaseModel):
    parent_id: int | None = None  # None = at the top of a space
    index: int = Field(default=0, ge=0)
    space_id: int | None = None  # with parent_id None: move it to this space


class SpaceBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class SpacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None
    clear_color: bool = False
    index: int | None = Field(default=None, ge=0)  # move the tab to this place


class CollectionsBulk(BaseModel):
    """One thing done to several picked collections."""

    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["move", "delete"]
    parent_id: int | None = None  # move: inside this collection...
    space_id: int | None = None  # ...or to the top of this space


UNSORTED_SQL = ("status = 'processed' AND NOT EXISTS "
                "(SELECT 1 FROM item_collections ic WHERE ic.item_id = items.id)")


def _counts(conn: sqlite3.Connection, platform: str | None = None) -> dict[str, int]:
    scoped, params = scope.where(platform, "items")
    row = conn.execute(
        f"""SELECT
             SUM(status = 'enriched') AS waiting,
             SUM(status = 'processed') AS processed,
             SUM({UNSORTED_SQL}) AS unsorted,
             SUM({UNSORTED_SQL} AND EXISTS (SELECT 1 FROM ai_results a WHERE a.item_id = items.id
                 AND a.suggestions_json NOT IN ('', '[]'))) AS suggested,
             SUM(status = 'processed' AND EXISTS (SELECT 1 FROM ai_results a WHERE a.item_id = items.id
                 AND a.tag_suggestions_json NOT IN ('', '[]'))) AS tag_suggested,
             SUM(status = 'processed' AND NOT EXISTS
                 (SELECT 1 FROM item_tags it WHERE it.item_id = items.id)) AS untagged,
             (SELECT COUNT(*) FROM item_collections ic JOIN items i ON i.id = ic.item_id
              WHERE ic.source = 'ai' AND i.deleted_at IS NULL) AS ai_filed,
             (SELECT COUNT(*) FROM item_tags it JOIN items i ON i.id = it.item_id
              WHERE it.source = 'ai' AND i.deleted_at IS NULL) AS ai_tagged
           FROM items WHERE {scoped}""",
        params,
    ).fetchone()
    keys = ("waiting", "processed", "unsorted", "suggested", "tag_suggested", "untagged", "ai_filed", "ai_tagged")
    return {key: int(row[key] or 0) for key in keys}


@router.get("/collections")
def list_collections(svc: AppServices = Depends(services)) -> dict[str, Any]:
    collections.seed_once(svc.db, svc.settings)
    chosen = scope.current(svc.settings)
    with svc.db.connect() as conn:
        return {
            "collections": collections.list_all(conn, chosen),
            "spaces": collections.spaces(conn),
            "counts": _counts(conn, chosen),
            "limit": collections.MAX_COLLECTIONS,  # in one space
            "per_save": collections.MAX_PER_ITEM,
            "space_limit": collections.MAX_SPACES,
            "depth_limit": collections.MAX_DEPTH,
        }


@router.post("/collections")
def create_collection(body: NewCollection, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            new_id = collections.create(conn, body.name, parent_id=body.parent_id, space_id=body.space_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc) | {"created_id": new_id}


@router.post("/collections/bulk")
def bulk_collections(body: CollectionsBulk, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Move or delete every picked collection. A collection picked together
    with the one it's inside moves along with it, so it is left alone."""
    try:
        with svc.db.connect() as conn:
            ids = [i for i in dict.fromkeys(body.ids) if collections.exists(conn, i)]
            if body.action == "delete":
                for collection_id in ids:
                    collections.delete(conn, collection_id)
            else:
                picked = set(ids)
                for collection_id in ids:
                    row = conn.execute("SELECT parent_id FROM collections WHERE id = ?", (collection_id,)).fetchone()
                    if row["parent_id"] in picked:
                        continue
                    collections.place(conn, collection_id, body.parent_id, 10_000, body.space_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc) | {"changed": len(ids)}


# ---------- spaces ----------


@router.post("/spaces")
def create_space(body: SpaceBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            new_id = collections.create_space(conn, body.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc) | {"created_space": new_id}


@router.patch("/spaces/{space_id}")
def change_space(space_id: int, body: SpacePatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            if not collections.space_exists(conn, space_id):
                raise HTTPException(status_code=404, detail="That space doesn't exist any more.")
            collections.update_space(conn, space_id, body.name, body.color, body.clear_color)
            if body.index is not None:
                collections.place_space(conn, space_id, body.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc)


@router.delete("/spaces/{space_id}")
def delete_space(space_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Delete a space; its collections move to the first other space."""
    try:
        with svc.db.connect() as conn:
            if not collections.space_exists(conn, space_id):
                raise HTTPException(status_code=404, detail="That space doesn't exist any more.")
            moved_to = collections.delete_space(conn, space_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc) | {"moved_to": moved_to}


class MergeBody(BaseModel):
    into_id: int


@router.post("/collections/{collection_id}/merge")
def merge_collection(collection_id: int, body: MergeBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Move every save into another collection and delete this one."""
    try:
        with svc.db.connect() as conn:
            require_collection(conn, collection_id)
            require_collection(conn, body.into_id)
            collections.merge(conn, collection_id, body.into_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc)


@router.patch("/collections/{collection_id}")
def change_collection(collection_id: int, body: CollectionPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Rename, describe, colour, fold, or let the AI use (or not use) a collection."""
    fields = body.model_dump(exclude_unset=True, exclude={"name", "clear_color"})
    if body.clear_color:
        fields["color"] = None
    try:
        with svc.db.connect() as conn:
            require_collection(conn, collection_id)
            if body.name is not None:
                collections.rename(conn, collection_id, body.name)
            collections.update(conn, collection_id, **fields)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if "icon" in fields:
        _forget_icon_file(svc, collection_id)  # a ready-made icon (or none) replaces an own picture
    return list_collections(svc)


class IconUpload(BaseModel):
    # The picture as a data address ("data:image/png;base64,..."), as the window reads a chosen file.
    data: str = Field(min_length=20, max_length=4_000_000)


ICON_SIZE = 192  # pixels; plenty for a folder tile


@router.post("/collections/{collection_id}/icon")
def upload_collection_icon(collection_id: int, body: IconUpload, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Put the user's own picture on a collection's folder. It is shrunk and
    kept as a PNG in the data folder; the original file isn't touched."""
    from PIL import Image, UnidentifiedImageError

    head, _, encoded = body.data.partition(",")
    if not head.startswith("data:image/") or ";base64" not in head:
        raise HTTPException(status_code=400, detail="That isn't a picture. Choose a PNG, JPG, WebP or GIF file.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in {"PNG", "JPEG", "WEBP", "GIF"}:
                raise HTTPException(status_code=400, detail="Choose a PNG, JPG, WebP or GIF picture.")
            picture.seek(0)
            small = picture.convert("RGBA")
            small.thumbnail((ICON_SIZE, ICON_SIZE))
    except HTTPException:
        raise
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=400, detail="That picture couldn't be read. Try another file.") from error
    with svc.db.connect() as conn:
        require_collection(conn, collection_id)
        folder = svc.paths.collection_icons
        folder.mkdir(parents=True, exist_ok=True)
        small.save(folder / f"{collection_id}.png", "PNG")
        collections.set_custom_icon(conn, collection_id, int(time.time() * 1000))
    return list_collections(svc)


@router.get("/collections/{collection_id}/icon")
def collection_icon(collection_id: int, svc: AppServices = Depends(services)) -> FileResponse:
    path = svc.paths.collection_icons / f"{collection_id}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="This collection has no picture of its own.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000"})


def _forget_icon_file(svc: AppServices, collection_id: int) -> None:
    try:
        (svc.paths.collection_icons / f"{collection_id}.png").unlink(missing_ok=True)
    except OSError:
        pass  # a leftover file does no harm


@router.post("/collections/{collection_id}/place")
def place_collection(collection_id: int, body: PlaceBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Drag a collection into a folder or to another spot in the sidebar."""
    try:
        with svc.db.connect() as conn:
            require_collection(conn, collection_id)
            collections.place(conn, collection_id, body.parent_id, body.index, body.space_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_collections(svc)


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_collection(conn, collection_id)
        collections.delete(conn, collection_id)
    _forget_icon_file(svc, collection_id)
    return list_collections(svc)


def require_collection(conn: sqlite3.Connection, collection_id: int) -> None:
    if not conn.execute("SELECT 1 FROM collections WHERE id = ?", (collection_id,)).fetchone():
        raise HTTPException(status_code=404, detail="No such collection.")


# ---------- items as cards ----------


def _extras(conn: sqlite3.Connection, item_ids: list[int]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """The tags, collections and plans of many saves, in three queries per
    500 saves instead of three per save."""
    found: dict[str, dict[int, list[dict[str, Any]]]] = {"tags": {}, "links": {}, "plans": {}}
    for start in range(0, len(item_ids), 500):
        chunk = item_ids[start : start + 500]
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(
            f"""SELECT it.item_id, t.id, t.name, t.color, it.source FROM item_tags it JOIN tags t ON t.id = it.tag_id
                WHERE it.item_id IN ({marks}) ORDER BY it.source = 'auto', it.created_at, t.name""",
            chunk,
        ):
            found["tags"].setdefault(int(row["item_id"]), []).append(
                {"id": row["id"], "name": row["name"], "color": row["color"], "source": row["source"]}
            )
        for row in conn.execute(
            f"""SELECT ic.item_id, c.id, c.name, c.origin, c.color, ic.source, ic.confidence
                FROM item_collections ic JOIN collections c ON c.id = ic.collection_id
                WHERE ic.item_id IN ({marks}) ORDER BY c.position, c.id""",
            chunk,
        ):
            link = dict(row)
            found["links"].setdefault(int(link.pop("item_id")), []).append(link)
        for row in conn.execute(
            f"""SELECT pi.item_id, p.id, p.name, pi.done FROM plan_items pi JOIN plans p ON p.id = pi.plan_id
                WHERE pi.item_id IN ({marks}) ORDER BY p.position, p.id""",
            chunk,
        ):
            found["plans"].setdefault(int(row["item_id"]), []).append(
                {"id": int(row["id"]), "name": row["name"], "done": bool(row["done"])}
            )
    return found


def cards_from_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Cards for a whole list of saves (rows from CARD_SQL), in their order."""
    extras = _extras(conn, [int(row["id"]) for row in rows])
    return [card_from_row(conn, row, extras) for row in rows]


def card_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row, extras: dict[str, dict[int, list[dict[str, Any]]]] | None = None
) -> dict[str, Any]:
    item = dict(row)
    steps = decode_json_list(item.get("steps_json"))
    if extras is None:
        extras = _extras(conn, [int(item["id"])])
    item_tags = extras["tags"].get(int(item["id"]), [])
    has = {tag["name"] for tag in item_tags}
    tag_ideas = [name for name in decode_json_list(item.get("tag_suggestions_json")) if name not in has]
    in_plans = extras["plans"].get(int(item["id"]), [])
    return {
        "id": item["id"],
        "platform": item["platform"],
        "platform_name": PLATFORM_NAMES.get(item["platform"], item["platform"]),
        "url": item["url"],
        "author": item["author"],
        "duration_s": item["duration_s"],
        "status": item["status"],
        "has_thumbnail": bool(item["thumbnail_path"]),
        "title": item["ai_title"] or item["title"] or item["description"] or item["caption"],
        "caption": item["description"] or item["caption"],
        "summary": item["summary"],
        "kind": item["kind"],
        "kind_label": KIND_LABELS.get(item["kind"] or "", None),
        "facts": decode_json_list(item.get("facts_json")),
        "steps": [step.get("text", "") if isinstance(step, dict) else str(step) for step in steps],
        # Ticks on the steps checklist, one per step (the item page and Plans).
        "steps_checked": [bool(step.get("done")) if isinstance(step, dict) else False for step in steps],
        "tags": [tag["name"] for tag in item_tags],
        "tag_list": item_tags,
        "suggestions": decode_json_list(item.get("suggestions_json")),
        "tag_suggestions": tag_ideas,
        "no_sound": bool(item.get("no_sound")),
        "gone": bool(item.get("gone_at")),
        "error": item["error"],
        "saved_at": item["saved_at"],
        "platform_collection": item["platform_collection"],
        "done": bool(item["done"]),
        "started_at": item["started_at"],
        "safe_to_unsave": bool(item["safe_to_unsave"] or item["deleted_at"]),
        "unsaved": bool(item["unsaved"]),
        "unsaved_at": item.get("unsaved_at"),
        "deleted": bool(item.get("deleted_at")),
        "deleted_at": item.get("deleted_at"),
        "collections": extras["links"].get(int(item["id"]), []),
        "plans": in_plans,
    }


CARD_SQL = """SELECT i.*, a.title AS ai_title, a.summary, a.kind, a.facts_json, a.steps_json, a.tags,
                      a.suggestions_json, a.tag_suggestions_json,
                      (SELECT t.text = '' FROM transcripts t WHERE t.item_id = i.id) AS no_sound
               FROM items i LEFT JOIN ai_results a ON a.item_id = i.id"""


@router.get("/library")
def library(
    view: Literal["collection", "unsorted", "waiting", "all"] = "all",
    collection_id: int | None = None,
    include_sub: bool = False,  # a folder: also the videos in the collections inside it
    svc: AppServices = Depends(services),
) -> list[dict[str, Any]]:
    where = {
        "unsorted": "i.status = 'processed' AND NOT EXISTS "
                    "(SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id)",
        "waiting": "i.status = 'enriched'",
        "all": "i.status = 'processed'",
        "collection": "EXISTS (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id AND ic.collection_id IN ({ids}))",
    }[view]
    params: list[Any] = []
    with svc.db.connect() as conn:
        if view == "collection":
            if collection_id is None:
                raise HTTPException(status_code=400, detail="Say which collection.")
            where = where.format(ids="?")
            params = [collection_id]
        scoped, scoped_params = scope.where(scope.current(svc.settings))
        rows = conn.execute(
            f"{CARD_SQL} WHERE {where} AND {scoped} ORDER BY i.saved_at DESC, i.id DESC LIMIT {PAGE_LIMIT}",
            [*params, *scoped_params],
        ).fetchall()
        return cards_from_rows(conn, rows)


def cards_by_id(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Item cards (as the Collections screen shows them) for these ids."""
    if not item_ids:
        return {}
    marks = ",".join("?" for _ in item_ids)
    rows = conn.execute(f"{CARD_SQL} WHERE i.id IN ({marks})", item_ids).fetchall()
    return {int(card["id"]): card for card in cards_from_rows(conn, rows)}


def one_card(conn: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    row = conn.execute(f"{CARD_SQL} WHERE i.id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No such item.")
    return card_from_row(conn, row)


class MoveBody(BaseModel):
    from_id: int | None = None
    to_id: int


@router.post("/items/{item_id}/move")
def move_item(item_id: int, body: MoveBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Drag and drop: take the item out of from_id (if given) and put it in to_id."""
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        require_collection(conn, body.to_id)
        try:
            collections.move(conn, item_id, body.from_id, body.to_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return one_card(conn, item_id)


@router.delete("/items/{item_id}/collections/{collection_id}")
def remove_from_collection(item_id: int, collection_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        collections.remove(conn, item_id, collection_id)
        return one_card(conn, item_id)


class AcceptBody(BaseModel):
    collection_id: int | None = None  # put it here; None = the AI's suggestion


def _suggested_id(conn: sqlite3.Connection, card: dict[str, Any]) -> int | None:
    """The collection the AI suggests for a save, if it still exists."""
    for pick in card["suggestions"]:
        row = collections.find(conn, str(pick.get("name") or "")) if isinstance(pick, dict) else None
        if row is not None:
            return int(row["id"])
    return None


@router.post("/review/{item_id}/accept")
def accept(item_id: int, body: AcceptBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Unsorted: put a save in the collection the AI suggests, or the one you pick."""
    with svc.db.connect() as conn:
        card = one_card(conn, item_id)
        target = body.collection_id if body.collection_id is not None else _suggested_id(conn, card)
        if target is None:
            raise HTTPException(status_code=400, detail="Pick a collection for this save.")
        require_collection(conn, target)
        try:
            collections.add_by_user(conn, item_id, target)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return one_card(conn, item_id)


@router.post("/review/accept-all")
def accept_all(svc: AppServices = Depends(services)) -> dict[str, int]:
    """Unsorted: accept the AI's suggestion for every save that has one."""
    scoped, params = scope.where(scope.current(svc.settings))
    done = 0
    with svc.db.connect() as conn:
        rows = conn.execute(
            f"""{CARD_SQL} WHERE i.status = 'processed' AND {scoped} AND NOT EXISTS
                (SELECT 1 FROM item_collections ic WHERE ic.item_id = i.id)
                AND a.suggestions_json NOT IN ('', '[]')""",
            params,
        ).fetchall()
        for card in cards_from_rows(conn, rows):
            target = _suggested_id(conn, card)
            if target is not None:
                collections.add_by_user(conn, int(card["id"]), target)
                done += 1
    return {"accepted": done}


class TagIdeasBody(BaseModel):
    names: list[str] = Field(min_length=1, max_length=20)
    accept: bool = True  # False: no thanks, forget these suggestions


@router.post("/items/{item_id}/tag-suggestions")
def answer_tag_suggestions(item_id: int, body: TagIdeasBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Accept the AI's suggested tags for a save (they become yours), or turn them down."""
    wanted = [tags.clean_tag(name) for name in body.names if tags.clean_tag(name)]
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        if body.accept:
            for name in wanted:
                try:
                    tags.add(conn, item_id, name, "user")
                except (tags.SaveFull, tags.TagsFull) as error:
                    raise HTTPException(status_code=400, detail=str(error)) from error
        row = conn.execute("SELECT tag_suggestions_json FROM ai_results WHERE item_id = ?", (item_id,)).fetchone()
        if row is not None:
            left = [name for name in decode_json_list(row["tag_suggestions_json"]) if name not in wanted]
            conn.execute("UPDATE ai_results SET tag_suggestions_json = ? WHERE item_id = ?", (json.dumps(left), item_id))
        return one_card(conn, item_id)


class ClearBody(BaseModel):
    """suggestions: forget every collection and tag the AI suggested;
    ai_tags: take off every tag the AI put on; ai_collections: take every
    save out of the collections the AI put it in (it goes back to Unsorted).
    Your own tags and placements always stay. Undo brings it all back."""

    what: Literal["suggestions", "ai_tags", "ai_collections"]


@router.post("/sorting/clear")
def clear_ai(body: ClearBody, svc: AppServices = Depends(services)) -> dict[str, int]:
    with svc.db.connect() as conn:
        if body.what == "suggestions":
            changed = conn.execute(
                "UPDATE ai_results SET suggestions_json = '[]', tag_suggestions_json = '[]' "
                "WHERE suggestions_json NOT IN ('', '[]') OR tag_suggestions_json NOT IN ('', '[]')"
            ).rowcount
        elif body.what == "ai_tags":
            changed = conn.execute("DELETE FROM item_tags WHERE source = 'ai'").rowcount
            tags.drop_unused(conn)
        else:
            changed = conn.execute("DELETE FROM item_collections WHERE source = 'ai'").rowcount
    return {"cleared": int(changed)}


# ---------- starting the AI jobs ----------


class StartBody(BaseModel):
    count: int | None = Field(default=20, ge=1)
    confirm_cost: bool = False


class ResortBody(BaseModel):
    which: Literal["all", "unsorted"] = "unsorted"
    item_ids: list[int] | None = Field(default=None, max_length=2000)  # just these saves
    keep_manual: bool = True
    confirm_cost: bool = False


@router.get("/notes/overview")
def notes_overview(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        counts = _counts(conn, scope.current(svc.settings))
    return {
        "counts": counts,
        "ai_label": svc.ai.current_label(),
        "is_cloud": svc.ai.is_cloud(),
        "cloud_batch_limit": CLOUD_BATCH_LIMIT,
    }


def _ready_or_error(svc: AppServices, provider: Provider, requests: int, confirmed: bool) -> JSONResponse | None:
    """Check the AI can run; for paid cloud AI, ask the user to confirm the cost first."""
    try:
        svc.ai.check_ready(provider)
    except AIError as error:
        return JSONResponse(status_code=400, content={"detail": str(error), "code": error.code})
    if provider.info.kind == "cloud" and not confirmed:
        return JSONResponse(
            status_code=409,
            content={
                "code": "confirm_cost",
                "requests": requests,
                "detail": (
                    f"This sends about {requests:,} request{'s' if requests != 1 else ''} to "
                    f"{provider.info.label} · {provider.model}, which your API key pays for (a few more if an answer needs fixing). "
                    "Continue?"
                ),
            },
        )
    return None


@router.post("/notes/start", response_model=None)
def start_notes(body: StartBody, svc: AppServices = Depends(services)) -> dict[str, Any] | JSONResponse:
    provider = svc.ai.provider()
    limit = body.count
    if provider.info.kind == "cloud":
        limit = min(limit or CLOUD_BATCH_LIMIT, CLOUD_BATCH_LIMIT)
    scoped, params = scope.where(scope.current(svc.settings), "items")
    with svc.db.connect() as conn:
        rows = conn.execute(
            f"SELECT id FROM items WHERE status = 'enriched' AND {scoped} ORDER BY saved_at DESC, id DESC LIMIT ?",
            (*params, limit if limit is not None else -1),
        ).fetchall()
    ids = [int(row["id"]) for row in rows]
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="No videos are waiting for notes. Get their transcripts first (Sort page).",
        )
    problem = _ready_or_error(svc, provider, len(ids), body.confirm_cost)
    if problem:
        return problem
    title = f"AI notes for {len(ids):,} video{'s' if len(ids) != 1 else ''}"
    job_id = svc.runner.submit("notes", title, _batch_params(provider, ids))
    return svc.jobs.get(job_id) or {}


def _batch_params(provider: Provider, ids: list[int]) -> dict[str, Any]:
    params: dict[str, Any] = {"item_ids": ids, "provider_id": provider.info.id}
    if provider.info.kind == "cloud":
        params["cloud_model"] = provider.model
    return params


def _pick_ids(svc: AppServices, which: str, item_ids: list[int] | None) -> list[int]:
    """The saves an AI button works on: the ones picked, or a group, for the
    platform chosen in the picker."""
    scoped, params = scope.where(scope.current(svc.settings), "items")
    groups = {
        "all": "status = 'processed'",
        "unsorted": UNSORTED_SQL,
        # Tags come with the notes; these are saves with notes but no tags.
        "untagged": "status = 'processed' AND NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.item_id = items.id)",
        "with_notes": "status IN ('enriched', 'processed')",
    }
    with svc.db.connect() as conn:
        if item_ids is not None:
            if not item_ids:
                return []
            marks = ",".join("?" for _ in item_ids)
            eligible = UNSORTED_SQL if which == "unsorted" else "status IN ('enriched', 'processed')"
            rows = conn.execute(
                f"SELECT id FROM items WHERE id IN ({marks}) AND {scoped} AND {eligible} "
                "ORDER BY saved_at DESC, id DESC",
                [*item_ids, *params],
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT id FROM items WHERE {groups[which]} AND {scoped} ORDER BY saved_at DESC, id DESC", params
            ).fetchall()
    return [int(row["id"]) for row in rows]


@router.post("/sorting/resort", response_model=None)
def resort(body: ResortBody, svc: AppServices = Depends(services)) -> dict[str, Any] | JSONResponse:
    ids = _pick_ids(svc, body.which, body.item_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="There's nothing to sort yet: the AI sorts saves once they have notes.")
    provider = svc.ai.provider()
    if provider.info.kind == "cloud":
        ids = ids[:CLOUD_BATCH_LIMIT]
    problem = _ready_or_error(svc, provider, len(ids), body.confirm_cost)
    if problem:
        return problem
    title = f"AI sort for {len(ids):,} video{'s' if len(ids) != 1 else ''}"
    params = _batch_params(provider, ids) | {"keep_manual": body.keep_manual, "since": now_iso()}
    job_id = svc.runner.submit("sort", title, params)
    return svc.jobs.get(job_id) or {}


class TagsBody(BaseModel):
    which: Literal["untagged", "with_notes"] = "untagged"
    item_ids: list[int] | None = Field(default=None, max_length=2000)
    confirm_cost: bool = False


@router.post("/tags/ai", response_model=None)
def ai_tags(body: TagsBody, svc: AppServices = Depends(services)) -> dict[str, Any] | JSONResponse:
    """The AI tags button: new tags from the AI for the picked saves (or every
    save without tags). The user's own tags stay."""
    ids = _pick_ids(svc, body.which, body.item_ids)
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="Nothing to tag: the AI suggests tags for saves once they have notes (Sort page).",
        )
    provider = svc.ai.provider()
    if provider.info.kind == "cloud":
        ids = ids[:CLOUD_BATCH_LIMIT]
    problem = _ready_or_error(svc, provider, len(ids), body.confirm_cost)
    if problem:
        return problem
    job_id = svc.runner.submit("tags", f"AI tags for {len(ids):,} video{'s' if len(ids) != 1 else ''}", _batch_params(provider, ids))
    return svc.jobs.get(job_id) or {}


# ---------- links from platform collections ----------


class LinkBody(BaseModel):
    platform: str
    name: str = Field(min_length=1, max_length=200)
    collection_id: int | None = None  # None = unlink
    mode: Literal["auto", "manual"] = "auto"
    create_collection: bool = False  # make an app collection with this name first
    space_id: int | None = None  # where that new collection goes
    parent_id: int | None = None  # ...or inside this collection


class TransferBody(BaseModel):
    """Bring every platform collection that isn't linked yet into the app."""

    space_id: int | None = None
    parent_id: int | None = None  # make them inside this collection
    platform: str | None = None  # only this platform's
    mode: Literal["auto", "manual"] = "auto"


class ApplyBody(BaseModel):
    platform: str
    name: str = Field(min_length=1, max_length=200)


class ImportDestinationBody(BaseModel):
    platform: str
    collection_id: int | None


@router.get("/platform-collections")
def list_platform_collections(space_id: int | None = None, svc: AppServices = Depends(services)) -> dict[str, Any]:
    collections.seed_once(svc.db, svc.settings)
    with svc.db.connect() as conn:
        return {
            "links": platform_links.overview(conn, scope.current(svc.settings)),
            "import_destinations": platform_links.import_destinations(conn),
            "room_left": collections.room_left(conn, space_id),
        }


@router.put("/platform-collections/default")
def change_import_destination(body: ImportDestinationBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    if body.platform not in PLATFORM_NAMES:
        raise HTTPException(status_code=400, detail="Unknown platform.")
    with svc.db.connect() as conn:
        if body.collection_id is not None:
            require_collection(conn, body.collection_id)
        platform_links.set_import_destination(conn, body.platform, body.collection_id)
        return {"import_destinations": platform_links.import_destinations(conn)}


@router.post("/platform-collections/transfer")
def transfer_platform_collections(body: TransferBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Every platform collection that isn't linked yet gets a collection of
    the same name in the app (an existing one with that name is reused) and
    is linked to it, so its saves are filed there now and after each import."""
    made = linked = filed = no_room = 0
    collections.seed_once(svc.db, svc.settings)
    with svc.db.connect() as conn:
        if body.parent_id is not None:
            require_collection(conn, body.parent_id)
        for entry in platform_links.overview(conn, body.platform or scope.current(svc.settings)):
            if entry["collection_id"] is not None:
                continue
            existed = collections.find(conn, entry["name"]) is not None
            try:
                target = collections.ensure(conn, entry["name"], "mine", body.parent_id, body.space_id)
            except ValueError:
                no_room += 1
                continue
            made += 0 if existed else 1
            linked += 1
            filed += platform_links.set_link(conn, entry["platform"], entry["name"], target, body.mode)
    return list_platform_collections(body.space_id, svc) | {
        "made": made, "linked": linked, "filed": filed, "no_room": no_room,
    }


@router.put("/platform-collections")
def link_platform_collection(body: LinkBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    if body.platform not in PLATFORM_NAMES:
        raise HTTPException(status_code=400, detail="Unknown platform.")
    try:
        with svc.db.connect() as conn:
            target = body.collection_id
            if body.create_collection:
                target = collections.ensure(conn, body.name, "mine", body.parent_id, body.space_id)
            elif target is not None:
                require_collection(conn, target)
            filed = platform_links.set_link(conn, body.platform, body.name, target, body.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_platform_collections(None, svc) | {"filed": filed}


@router.post("/platform-collections/apply")
def apply_platform_collection(body: ApplyBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """"Add now" for a manual link: file its saves straight away."""
    try:
        with svc.db.connect() as conn:
            filed = platform_links.apply(conn, body.platform, body.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_platform_collections(None, svc) | {"filed": filed}
