"""Transcripts routes: what's waiting, start a batch, recent results, settings."""

from __future__ import annotations

import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.enrich.job import DEVICE_KEY, DEVICES, MODEL_KEY, now_iso
from app.enrich.speech_models import DEFAULT_MODEL, MODELS, is_downloaded
from app.enrich.tiktok_session import MAX_SESSION_BYTES
from app.importers import PLATFORM_NAMES
from app.services import AppServices, services

router = APIRouter(prefix="/api")

PREVIEW_CHARS = 280
FAILED = """(i.status = 'failed' OR (
    i.error LIKE 'Got the details,%'
    AND NOT EXISTS (SELECT 1 FROM transcripts t WHERE t.item_id = i.id)
))"""
NO_SPEECH = "EXISTS (SELECT 1 FROM transcripts t WHERE t.item_id = i.id AND t.text = '')"
TARGETS = {
    "waiting": "i.gone_at IS NULL AND i.status = 'imported'",
    "failed": f"i.gone_at IS NULL AND i.status <> 'imported' AND {FAILED}",
    "no_speech": f"i.gone_at IS NULL AND {NO_SPEECH}",
    "unavailable": "i.gone_at IS NOT NULL",
}


class StartBody(BaseModel):
    # How many videos to do; None = all of them.
    count: int | None = Field(default=5, ge=1)
    which: Literal["waiting", "failed", "no_speech", "unavailable"] = "waiting"
    item_id: int | None = Field(default=None, ge=1)


class SpeechSettings(BaseModel):
    model: str | None = None
    device: str | None = None


def _counts(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM items WHERE deleted_at IS NULL AND gone_at IS NULL GROUP BY status"
    ).fetchall()
    by_status = {row["status"]: int(row["n"]) for row in rows}
    no_speech = conn.execute(
        f"SELECT COUNT(*) FROM items i WHERE i.deleted_at IS NULL AND {TARGETS['no_speech']}"
    ).fetchone()[0]
    gone = conn.execute("SELECT COUNT(*) FROM items WHERE gone_at IS NOT NULL AND deleted_at IS NULL").fetchone()[0]
    reasons = conn.execute(
        f"""SELECT coalesce(error, 'No reason given.') AS text, COUNT(*) AS n FROM items i
            WHERE i.deleted_at IS NULL AND {TARGETS['failed']} GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()
    return {
        "total": sum(by_status.values()),
        "waiting": by_status.get("imported", 0),
        "done": by_status.get("enriched", 0) + by_status.get("processed", 0),
        "failed": sum(int(row["n"]) for row in reasons),
        "no_speech": int(no_speech),
        "gone": int(gone),
        "failed_reasons": [{"text": row["text"], "count": int(row["n"])} for row in reasons[:6]],
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
    return {"counts": counts, "speech": _speech(svc), "tiktok_session": bool(svc.tiktok_session.cookies())}


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


@router.put("/enrich/tiktok-session")
async def connect_tiktok(request: Request, svc: AppServices = Depends(services)) -> dict[str, bool]:
    if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
        raise HTTPException(status_code=415, detail="Choose a TikTok session file.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_SESSION_BYTES:
            raise HTTPException(status_code=413, detail="Choose a session file containing only TikTok cookies.")
        content.extend(chunk)
    try:
        svc.tiktok_session.load(content.decode("utf-8"))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Choose a TikTok cookies.txt file in Netscape format.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    return {"connected": True}


@router.delete("/enrich/tiktok-session")
def disconnect_tiktok(svc: AppServices = Depends(services)) -> dict[str, bool]:
    svc.tiktok_session.clear()
    return {"connected": False}


@router.post("/enrich/start")
def start(body: StartBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    since = now_iso()
    limit = body.count if body.count is not None else -1  # -1 = no limit in SQLite
    target = TARGETS[body.which]
    params: tuple[int, ...] = (limit,)
    if body.item_id is not None:
        target += " AND i.id = ?"
        params = (body.item_id, limit)
    with svc.db.connect() as conn:
        rows = conn.execute(
            f"SELECT i.id FROM items i WHERE i.deleted_at IS NULL AND {target} "
            "ORDER BY i.saved_at DESC, i.id DESC LIMIT ?",
            params,
        ).fetchall()
    ids = [int(row["id"]) for row in rows]
    if not ids:
        raise HTTPException(status_code=400, detail="There are no matching videos to try.")
    job_params: dict[str, Any] = {"item_ids": ids}
    count = f"{len(ids):,} video{'s' if len(ids) != 1 else ''}"
    title = f"Transcripts for {count}"
    if body.which != "waiting":
        job_params["retry_since"] = since
        title = f"Retry {count}"
    job_id = svc.runner.submit("enrich", title, job_params)
    return svc.jobs.get(job_id) or {}


@router.get("/enrich/problems")
def problems(offset: int = 0, svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Unreadable and unavailable videos with their last recorded reason."""
    condition = "deleted_at IS NULL AND (status = 'failed' OR gone_at IS NOT NULL OR (enriched_at IS NOT NULL AND error IS NOT NULL))"
    with svc.db.connect() as conn:
        count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition}").fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, coalesce(title, caption, url) AS title, error, gone_at IS NOT NULL AS unavailable
                FROM items WHERE {condition} ORDER BY id DESC LIMIT 50 OFFSET ?""", (max(0, offset),),
        ).fetchall()
    return {"total": count, "items": [dict(row) | {"unavailable": bool(row["unavailable"])} for row in rows]}


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
