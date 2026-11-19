"""Routes for Settings -> Storage: see what takes up space, and delete it."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import storage
from app.enrich.job import MODEL_KEY
from app.enrich.speech_models import DEFAULT_MODEL
from app.jobs.runner import JobsBusy
from app.services import AppServices, services

router = APIRouter(prefix="/api/storage")


def _chosen_speech_model(svc: AppServices) -> str:
    return str(svc.settings.get(MODEL_KEY, DEFAULT_MODEL) or DEFAULT_MODEL)


def _chosen_ollama_model(svc: AppServices) -> str | None:
    return svc.ai.model_for("ollama") if svc.ai.current_id() == "ollama" else None


@router.get("")
def list_storage(svc: AppServices = Depends(services)) -> dict[str, Any]:
    paths = svc.paths
    entries = storage.ollama_entries(svc.ai.http, svc.ai.base_url_for("ollama"), _chosen_ollama_model(svc))
    entries += storage.local_entries(
        paths.models, paths.audio, paths.imports, paths.thumbnails, paths.database, _chosen_speech_model(svc)
    )
    backups = paths.root / "backups"
    with svc.db.connect() as conn:
        saves = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
        has_library_data = saves > 0 or any(
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None
            for table in ("collections", "tags", "plans", "chats", "removed_links", "undo_log")
        )
    return {
        "entries": storage.as_dicts(entries),
        "data_folder": str(paths.root),
        # For "Clear my data": what there is to clear.
        "saves": saves,
        "has_library_data": has_library_data,
        "backups": len(list(backups.glob("*.db"))) if backups.is_dir() else 0,
        "backups_bytes": storage.folder_bytes(backups),
    }


class ClearBody(BaseModel):
    # "backups": the database copies kept before updates.
    # "saves": every save with its transcript, notes, collections, tags, plans and chats.
    # "everything": both, and the log. Models and settings always stay.
    what: Literal["backups", "saves", "everything"]
    confirmation: str = ""


@router.post("/clear")
def clear_data(body: ClearBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Delete the user's own data for good. Nothing is copied first."""
    paths = svc.paths
    cleared: dict[str, int] = {}
    if body.what in ("saves", "everything"):
        if body.confirmation.strip() != "DELETE":
            raise HTTPException(status_code=400, detail="Type DELETE to confirm clearing your library.")
        try:
            with svc.runner.maintenance():
                with svc.db.connect() as conn:
                    cleared["saves"] = storage.clear_saves(
                        conn, [paths.thumbnails, paths.audio, paths.imports, paths.collection_icons]
                    )
                with svc.db.connect() as conn:
                    conn.isolation_level = None
                    conn.execute("VACUUM")  # reclaim freed space
        except JobsBusy as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    if body.what in ("backups", "everything"):
        cleared["backups"] = storage.clear_backups(paths.root / "backups")
    if body.what == "everything":
        for log in paths.logs.glob("*.log*"):
            try:
                log.write_text("", encoding="utf-8")
            except OSError:
                pass
    return list_storage(svc) | {"cleared": cleared}


@router.delete("/{entry_id:path}")
def delete_entry(entry_id: str, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        with svc.runner.maintenance():
            if entry_id.startswith("ollama:"):
                storage.delete_ollama(svc.ai.http, svc.ai.base_url_for("ollama"), entry_id.split(":", 1)[1])
            else:
                if entry_id == "search-model":
                    svc.search.forget_model()
                storage.delete_local(entry_id, svc.paths.models, svc.paths.audio, svc.paths.imports)
    except JobsBusy as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except storage.StorageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return list_storage(svc)
