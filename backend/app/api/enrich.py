"""Transcripts routes: what's waiting, start a batch, recent results, settings."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.enrich.job import DEVICE_KEY, DEVICES, MODEL_KEY
from app.enrich.speech_models import DEFAULT_MODEL, MODELS, is_downloaded
from app.importers import PLATFORM_NAMES
from app.services import AppServices, services

router = APIRouter(prefix="/api")

PREVIEW_CHARS = 280


class StartBody(BaseModel):
    # How many videos to do; None = all of them.
    count: int | None = Field(default=5, ge=1)
    # "waiting" = not done yet; "failed" = try the ones that failed again.
    which: str = "waiting"


class SpeechSettings(BaseModel):
    model: str | None = None
    device: str | None = None


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM items WHERE deleted_at IS NULL GROUP BY status").fetchall()
    by_status = {row["status"]: int(row["n"]) for row in rows}
    no_speech = conn.execute(
        "SELECT COUNT(*) FROM transcripts WHERE text = ''"
    ).fetchone()[0]
    return {
        "total": sum(by_status.values()),
        "waiting": by_status.get("imported", 0),
        "done": by_status.get("enriched", 0) + by_status.get("processed", 0),
        "failed": by_status.get("failed", 0),
        "no_speech": int(no_speech),
    }


def _speech(svc: AppServices) -> dict[str, Any]:
    chosen = svc.settings.get(MODEL_KEY, DEFAULT_MODEL)
    return {
        "model": chosen if chosen in MODELS else DEFAULT_MODEL,
        "device": svc.settings.get(DEVICE_KEY, "auto"),
        "models": [
            {
                "id": model.id,
                "label": model.label,
                "approx_bytes": model.approx_bytes,
                "hint": model.hint,
                "downloaded": is_downloaded(svc.paths.models, model.id),
            }
            for model in MODELS.values()
        ],
    }


@router.get("/enrich")
def overview(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        counts = _counts(conn)
    return {"counts": counts, "speech": _speech(svc)}


@router.put("/enrich/settings")
def change_settings(body: SpeechSettings, svc: AppServices = Depends(services)) -> dict[str, Any]:
    if body.model is not None:
        if body.model not in MODELS:
            raise HTTPException(status_code=400, detail="That speech model isn't one of the choices.")
        svc.settings.set(MODEL_KEY, body.model)
    if body.device is not None:
        if body.device not in DEVICES:
            raise HTTPException(status_code=400, detail="Pick 'auto' or 'cpu'.")
        svc.settings.set(DEVICE_KEY, body.device)
    return _speech(svc)


@router.post("/enrich/start")
def start(body: StartBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    status = {"waiting": "imported", "failed": "failed"}.get(body.which)
    if status is None:
        raise HTTPException(status_code=400, detail="'which' must be 'waiting' or 'failed'.")
    limit = body.count if body.count is not None else -1  # -1 = no limit in SQLite
    with svc.db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM items WHERE status = ? AND deleted_at IS NULL ORDER BY saved_at DESC, id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    ids = [int(row["id"]) for row in rows]
    if not ids:
        detail = (
            "Every imported video already has its transcript. Import more saves first."
            if body.which == "waiting"
            else "No videos failed, so there's nothing to try again."
        )
        raise HTTPException(status_code=400, detail=detail)
    title = f"Transcripts for {len(ids):,} video{'s' if len(ids) != 1 else ''}"
    if body.which == "failed":
        title = f"Try {len(ids):,} failed video{'s' if len(ids) != 1 else ''} again"
    job_id = svc.runner.submit("enrich", title, {"item_ids": ids})
    return svc.jobs.get(job_id) or {}


@router.get("/enrich/recent")
def recent(limit: int = 12, svc: AppServices = Depends(services)) -> list[dict[str, Any]]:
    """The most recently processed videos, newest first."""
    limit = max(1, min(limit, 100))
    with svc.db.connect() as conn:
        rows = conn.execute(
            """SELECT i.id, i.platform, i.url, i.title, i.description, i.caption, i.author,
                      i.duration_s, i.enrich_seconds, i.enriched_at, i.status, i.error,
                      i.thumbnail_path, t.text AS transcript, t.language
               FROM items i LEFT JOIN transcripts t ON t.item_id = i.id
               WHERE i.enriched_at IS NOT NULL AND i.deleted_at IS NULL
               ORDER BY i.enriched_at DESC, i.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        transcript = row["transcript"]
        result.append({
            "id": row["id"],
            "platform": row["platform"],
            "platform_name": PLATFORM_NAMES.get(row["platform"], row["platform"]),
            "url": row["url"],
            "title": row["title"] or row["caption"] or row["description"],
            "author": row["author"],
            "duration_s": row["duration_s"],
            "seconds": row["enrich_seconds"],
            "status": row["status"],
            "error": row["error"],
            "has_thumbnail": bool(row["thumbnail_path"]),
            "transcript_preview": (transcript or "")[:PREVIEW_CHARS] or None,
            "transcript_chars": len(transcript) if transcript is not None else None,
            "no_speech": transcript == "",
            "language": row["language"],
        })
    return result


@router.get("/items/{item_id}/thumbnail")
def thumbnail(item_id: int, svc: AppServices = Depends(services)) -> FileResponse:
    with svc.db.connect() as conn:
        row = conn.execute("SELECT thumbnail_path FROM items WHERE id = ?", (item_id,)).fetchone()
    name = row["thumbnail_path"] if row else None
    folder = svc.paths.thumbnails.resolve()
    path = (folder / name).resolve() if name else None
    if path is None or not path.is_relative_to(folder) or not path.is_file():
        raise HTTPException(status_code=404, detail="No thumbnail for this item yet.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
