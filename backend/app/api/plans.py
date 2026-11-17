"""Routes for Plans: make a plan from one save or many, tick saves off,
reorder, rename and finish plans."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.sorting import collections
from app.api.sorting import cards_by_id
from app.library import plans
from app.services import AppServices, services

router = APIRouter(prefix="/api")


class NewPlan(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    item_ids: list[int] = Field(default_factory=list, max_length=plans.MAX_ITEMS)
    collection_id: int | None = None  # start it with everything in this collection
    due_on: str | None = None


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    color: str | None = None
    done: bool | None = None
    due_on: str | None = None  # "2026-12-24"; null clears it
    pinned: bool | None = None


class PlanItemPatch(BaseModel):
    section: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=300)


class NewTask(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    section: str | None = Field(default=None, max_length=40)


class TaskPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=200)
    section: str | None = Field(default=None, max_length=40)
    done: bool | None = None


class SectionRename(BaseModel):
    old: str = Field(min_length=1, max_length=40)
    new: str | None = Field(default=None, max_length=40)  # null: dissolve the section


class ItemsBody(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=plans.MAX_ITEMS)


class TickBody(BaseModel):
    done: bool


def require_plan(conn: Any, plan_id: int) -> None:
    if not plans.exists(conn, plan_id):
        raise HTTPException(status_code=404, detail="That plan doesn't exist any more.")


@router.get("/plans")
def list_plans(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        found = plans.list_all(conn)
    return {
        "plans": found,
        "open": sum(1 for plan in found if not plan["done"]),
        "finished": sum(1 for plan in found if plan["done"]),
    }


@router.post("/plans")
def create_plan(body: NewPlan, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            ids = list(body.item_ids)
            if body.collection_id is not None:
                inside = collections.descendants(conn, body.collection_id)
                marks = ",".join("?" for _ in inside)
                ids += [int(r["id"]) for r in conn.execute(
                    f"""SELECT DISTINCT i.id FROM items i JOIN item_collections ic ON ic.item_id = i.id
                        WHERE ic.collection_id IN ({marks}) AND i.deleted_at IS NULL
                        ORDER BY i.saved_at DESC, i.id DESC LIMIT {plans.MAX_ITEMS}""", inside)]
            plan_id = plans.create(conn, body.name, body.note, ids[: plans.MAX_ITEMS])
            if body.due_on:
                plans.update(conn, plan_id, due_on=body.due_on)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return plan_details(plan_id, svc)


@router.get("/plans/{plan_id}")
def plan_details(plan_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        row = plans.get(conn, plan_id)
        if row is None:
            raise HTTPException(status_code=404, detail="That plan doesn't exist any more.")
        entries = plans.item_rows(conn, plan_id)
        cards = cards_by_id(conn, [int(e["item_id"]) for e in entries])
        summary = plans.summary(conn, row)
        todo = plans.tasks(conn, plan_id)
    shown = [e for e in entries if int(e["item_id"]) in cards and not cards[int(e["item_id"])]["deleted"]]
    # Sections in the order they first appear (saves, then to-dos).
    sections = list(dict.fromkeys(s for s in [*(e["section"] for e in shown), *(t["section"] for t in todo)] if s))
    return summary | {
        "items": [
            {"item": cards[int(e["item_id"])], "done": bool(e["done"]), "done_at": e["done_at"],
             "section": e["section"], "note": e["note"]}
            for e in shown
        ],
        "tasks": todo,
        "sections": sections,
    }


@router.patch("/plans/{plan_id}")
def change_plan(plan_id: int, body: PlanPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            require_plan(conn, plan_id)
            plans.update(conn, plan_id, **body.model_dump(exclude_unset=True))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return plan_details(plan_id, svc)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Delete a plan. Its saves stay in the app."""
    with svc.db.connect() as conn:
        plans.delete(conn, plan_id)
    return list_plans(svc)


@router.post("/plans/{plan_id}/items")
def add_to_plan(plan_id: int, body: ItemsBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            require_plan(conn, plan_id)
            added = plans.add_items(conn, plan_id, body.item_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return plan_details(plan_id, svc) | {"added": added}


@router.delete("/plans/{plan_id}/items/{item_id}")
def remove_from_plan(plan_id: int, item_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        plans.remove_item(conn, plan_id, item_id)
    return plan_details(plan_id, svc)


@router.put("/plans/{plan_id}/items/{item_id}")
def tick_plan_item(plan_id: int, item_id: int, body: TickBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        try:
            plans.tick_item(conn, plan_id, item_id, body.done)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    return plan_details(plan_id, svc)


@router.patch("/plans/{plan_id}/items/{item_id}")
def change_plan_item(plan_id: int, item_id: int, body: PlanItemPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Put a save in a section of the plan, or write a note on it."""
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        try:
            plans.set_item(conn, plan_id, item_id, **body.model_dump(exclude_unset=True))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    return plan_details(plan_id, svc)


@router.post("/plans/{plan_id}/tasks")
def add_plan_task(plan_id: int, body: NewTask, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            require_plan(conn, plan_id)
            plans.add_task(conn, plan_id, body.text, body.section)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return plan_details(plan_id, svc)


@router.patch("/plans/{plan_id}/tasks/{task_id}")
def change_plan_task(plan_id: int, task_id: int, body: TaskPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.db.connect() as conn:
            require_plan(conn, plan_id)
            plans.update_task(conn, plan_id, task_id, **body.model_dump(exclude_unset=True))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return plan_details(plan_id, svc)


@router.delete("/plans/{plan_id}/tasks/{task_id}")
def delete_plan_task(plan_id: int, task_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        plans.delete_task(conn, plan_id, task_id)
    return plan_details(plan_id, svc)


@router.post("/plans/{plan_id}/sections")
def rename_plan_section(plan_id: int, body: SectionRename, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        plans.rename_section(conn, plan_id, body.old, body.new)
    return plan_details(plan_id, svc)


@router.post("/plans/{plan_id}/copy")
def copy_plan(plan_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        new_id = plans.copy(conn, plan_id)
    return plan_details(new_id, svc)


@router.post("/plans/{plan_id}/order")
def reorder_plan(plan_id: int, body: ItemsBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        require_plan(conn, plan_id)
        plans.reorder(conn, plan_id, body.item_ids)
    return plan_details(plan_id, svc)
