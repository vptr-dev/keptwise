"""Routes for tags (list, add to a save, rename/merge, colour, delete) and
for doing one thing to many saves at once (the Library's "Select")."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.sorting import collections, tags
from app.api.library import remove_files
from app.api.sorting import cards_by_id, one_card, require_collection
from app.library import plans, progress, scope
from app.services import AppServices, services

router = APIRouter(prefix="/api")

MAX_BULK = 2000
TAG_COLORS = ("accent", "violet", "indigo", "blue", "teal", "emerald", "amber", "rose", "zinc")


# ---------- tags ----------


@router.get("/tags")
def list_tags(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Every tag, counted for the platform chosen in the picker."""
    with svc.db.connect() as conn:
        return {
            "tags": tags.list_all(conn, scope.current(svc.settings)),
            "per_save": tags.MAX_PER_ITEM,
            "limit": tags.MAX_TAGS,
            "total": tags.total(conn),  # every tag, whatever platform is picked
        }


class TagGroup(BaseModel):
    tag_ids: list[int] = Field(min_length=1, max_length=500)
    into: str | None = Field(default=None, max_length=40)  # merge: the name they all become


@router.post("/tags/merge")
def merge_tags(body: TagGroup, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Make several tags one (e.g. "pasta", "pastas" and "pasta recipe" -> "pasta")."""
    name = tags.clean_tag(body.into or "")
    if not name:
        raise HTTPException(status_code=400, detail="Type the name they should all become.")
    with svc.db.connect() as conn:
        for tag_id in body.tag_ids:
            if conn.execute("SELECT 1 FROM tags WHERE id = ?", (tag_id,)).fetchone():
                tags.rename(conn, tag_id, name)
    return list_tags(svc)


@router.post("/tags/delete")
def delete_tags(body: TagGroup, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        for tag_id in body.tag_ids:
            tags.delete(conn, tag_id)
    return list_tags(svc)


class TagName(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@router.post("/tags")
def create_tag(body: TagName, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            created = tags.ensure(conn, body.name)
            # A new, empty tag would be tidied away; a colour keeps it.
            conn.execute("UPDATE tags SET color = coalesce(color, 'zinc') WHERE id = ?", (created,))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_tags(svc) | {"created_id": created}


class TagPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None


@router.patch("/tags/{tag_id}")
def change_tag(tag_id: int, body: TagPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Rename a tag (if the new name is taken, the two tags become one) or recolour it."""
    with svc.db.connect() as conn:
        if not conn.execute("SELECT 1 FROM tags WHERE id = ?", (tag_id,)).fetchone():
            raise HTTPException(status_code=404, detail="No such tag.")
        if body.color is not None:
            if body.color not in TAG_COLORS:
                raise HTTPException(status_code=400, detail="Unknown colour.")
            tags.set_color(conn, tag_id, body.color)
        if body.name is not None:
            try:
                tags.rename(conn, tag_id, body.name)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
    return list_tags(svc)


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        tags.delete(conn, tag_id)
    return list_tags(svc)


@router.post("/items/{item_id}/tags")
def tag_item(item_id: int, body: TagName, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        try:
            tags.add(conn, item_id, body.name, "user")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return one_card(conn, item_id)


@router.delete("/items/{item_id}/tags/{tag_id}")
def untag_item(item_id: int, tag_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        one_card(conn, item_id)
        tags.remove(conn, item_id, tag_id)
        tags.drop_unused(conn)
        return one_card(conn, item_id)


# ---------- many saves at once ----------


class BulkBody(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=MAX_BULK)
    action: Literal[
        "add_to", "move_to", "remove_from", "add_tag", "remove_tag", "done", "not_done", "add_to_plan",
        "safe", "not_safe", "unsaved", "still_saved", "delete", "restore", "purge",
    ]
    collection_id: int | None = None  # for add_to / move_to / remove_from
    plan_id: int | None = None  # for add_to_plan
    from_id: int | None = None  # move_to: the collection they're shown in
    tag: str | None = Field(default=None, max_length=40)  # for add_tag / remove_tag


@router.post("/items/bulk")
def bulk(body: BulkBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Do the same thing to every selected save. Returns the changed cards."""
    ids = list(dict.fromkeys(body.item_ids))
    with svc.db.connect() as conn:
        marks = ",".join("?" for _ in ids)
        found = {int(r["id"]) for r in conn.execute(f"SELECT id FROM items WHERE id IN ({marks})", ids)}
        if not found:
            raise HTTPException(status_code=404, detail="None of those saves exist any more.")
        ids = [item_id for item_id in ids if item_id in found]
        if body.action in ("add_to", "move_to", "remove_from"):
            if body.collection_id is None:
                raise HTTPException(status_code=400, detail="Pick a collection.")
            require_collection(conn, body.collection_id)
        if body.action in ("add_tag", "remove_tag") and not tags.clean_tag(body.tag or ""):
            raise HTTPException(status_code=400, detail="Type a tag.")
        if body.action == "add_tag":
            try:
                tags.ensure(conn, body.tag or "")  # a new tag needs room in the list first
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
        if body.action == "add_to_plan":
            if body.plan_id is None or not plans.exists(conn, body.plan_id):
                raise HTTPException(status_code=400, detail="Pick a plan.")
            try:
                plans.add_items(conn, body.plan_id, ids)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
        full = 0
        purged: dict[int, list[str]] = {}
        tag_row = tags.find(conn, body.tag or "") if body.action == "remove_tag" else None
        for item_id in ids:
            if body.action in ("add_to", "move_to"):
                try:
                    if body.action == "add_to":
                        collections.add_by_user(conn, item_id, body.collection_id)  # type: ignore[arg-type]
                    else:
                        collections.move(conn, item_id, body.from_id, body.collection_id)  # type: ignore[arg-type]
                except collections.SaveFull:
                    full += 1  # that save is already in the most collections allowed
            elif body.action == "remove_from":
                collections.remove(conn, item_id, body.collection_id)  # type: ignore[arg-type]
            elif body.action == "add_tag":
                try:
                    tags.add(conn, item_id, body.tag or "", "user")
                except ValueError:
                    full += 1  # that save already has the most tags allowed
            elif body.action == "remove_tag" and tag_row is not None:
                tags.remove(conn, item_id, int(tag_row["id"]))
            elif body.action in ("done", "not_done"):
                progress.set_done(conn, item_id, body.action == "done")
            elif body.action in ("safe", "not_safe"):
                progress.set_safe(conn, item_id, body.action == "safe")
            elif body.action in ("unsaved", "still_saved"):
                progress.set_unsaved(conn, item_id, body.action == "unsaved")
            elif body.action in ("delete", "restore"):
                progress.set_deleted(conn, item_id, body.action == "delete")
            elif body.action == "purge":
                # Only saves that are already in the Archive can go for good.
                if conn.execute("SELECT deleted_at FROM items WHERE id = ?", (item_id,)).fetchone()["deleted_at"]:
                    purged[item_id] = progress.purge(conn, item_id)
        if body.action == "remove_tag":
            tags.drop_unused(conn)
        cards = cards_by_id(conn, [item_id for item_id in ids if item_id not in purged])
    for item_id, names in purged.items():
        remove_files(svc, item_id, names)
    return {
        "changed": len(ids) - full,
        "skipped_full": full,
        "items": [cards[item_id] for item_id in ids if item_id in cards],
    }
