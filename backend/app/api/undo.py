"""Routes for the Undo and Redo buttons (app/db/undo.py does the work)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.services import AppServices, services

router = APIRouter(prefix="/api")


def _history(svc: AppServices) -> Any:
    if svc.db.undo is None:
        raise HTTPException(status_code=409, detail="Undo isn't available.")
    return svc.db.undo


@router.get("/undo")
def undo_state(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _history(svc).state()


@router.post("/undo")
def undo(expected_id: int | None = None, svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _replay(svc, "undo", expected_id)


@router.post("/redo")
def redo(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _replay(svc, "redo")


def _replay(svc: AppServices, which: str, expected_id: int | None = None) -> dict[str, Any]:
    history = _history(svc)
    try:
        label = history.undo(expected_id) if which == "undo" else history.redo()
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"done": label, **history.state()}
