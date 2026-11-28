"""Job routes: list jobs, pause/resume/cancel, and the live update stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.ai.sorting.job import needs_ai_work, now_iso
from app.db.items_repo import get_item_row
from app.enrich.job import needs_enrichment
from app.services import AppServices, services

router = APIRouter(prefix="/api")

# How long one wait for news lasts before sending a keep-alive (seconds).
# Short, so closing the app never waits long for this stream.
WAIT_SECONDS = 2.0


@router.get("/jobs")
def list_jobs(svc: AppServices = Depends(services)) -> list[dict[str, Any]]:
    return svc.jobs.recent()


@router.get("/jobs/{job_id}")
def get_job(job_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    job = svc.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return job


@router.get("/jobs/{job_id}/remaining")
def remaining(job_id: int, svc: AppServices = Depends(services)) -> list[dict[str, Any]]:
    job = get_job(job_id, svc)
    params = job["params"]
    kind = job["kind"]
    if kind not in ("enrich", "notes", "sort", "tags"):
        return []
    retry_since = datetime.fromisoformat(params["retry_since"]) if params.get("retry_since") else None
    started = str(params.get("since") or now_iso())
    tagged = set(params.get("tagged_ids", []))
    results = []
    with svc.db.connect() as conn:
        for item_id in params.get("item_ids", []):
            row = get_item_row(conn, int(item_id))
            if row is None or item_id in tagged:
                continue
            eligible = needs_enrichment(row, retry_since) if kind == "enrich" else needs_ai_work(row, kind, started)
            if eligible:
                results.append({"id": row["id"], "title": row["title"] or row["caption"] or row["url"],
                                "error": row["error"], "unavailable": bool(row["gone_at"])})
    return results


def _require(svc: AppServices, job_id: int) -> None:
    if svc.jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="No such job.")


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    _require(svc, job_id)
    svc.runner.pause(job_id)
    return svc.jobs.get(job_id) or {}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    _require(svc, job_id)
    svc.runner.resume(job_id)
    return svc.jobs.get(job_id) or {}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    _require(svc, job_id)
    svc.runner.cancel(job_id)
    return svc.jobs.get(job_id) or {}


@router.post("/jobs/{job_id}/dismiss-notice", status_code=204)
def dismiss_notice(job_id: int, svc: AppServices = Depends(services)) -> None:
    if not svc.jobs.dismiss_notice(job_id):
        _require(svc, job_id)
        raise HTTPException(status_code=409, detail="This job is still active.")


def _sse(event_type: str, data: Any, seq: int | None = None) -> str:
    lines = []
    if seq is not None:
        lines.append(f"id: {seq}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


@router.get("/events")
async def events(
    request: Request,
    after: int = -1,
    once: bool = False,
    svc: AppServices = Depends(services),
) -> StreamingResponse:
    """Server-Sent Events: the UI gets every job update as it happens.

    after: only send events newer than this number (-1 = only new ones).
    once:  stop after the first batch (used by tests).
    """
    hub = svc.hub

    async def stream() -> AsyncIterator[str]:
        last = hub.last_seq if after < 0 else after
        yield _sse("ready", {"seq": last})
        while not hub.closed:
            if await request.is_disconnected():
                return
            batch = await asyncio.to_thread(hub.wait_for, last, WAIT_SECONDS)
            if not batch:
                yield ": keep-alive\n\n"
                continue
            for event in batch:
                last = event.seq
                yield _sse(event.type, event.data, event.seq)
            if once:
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
