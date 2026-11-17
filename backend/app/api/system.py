"""Basic routes: is the server up, and a hello message for the UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import __version__
from app.services import AppServices, services
from app.updater import can_update_itself

# Routes anyone on this PC may call (no session token needed).
public_router = APIRouter(prefix="/api")

# Routes that need the session token (main.py adds the check).
router = APIRouter(prefix="/api")


class Health(BaseModel):
    status: str
    version: str


class Hello(BaseModel):
    message: str
    version: str


@public_router.get("/health")
def health() -> Health:
    """The launcher polls this to know when the server is ready."""
    return Health(status="ok", version=__version__)


@router.get("/hello")
def hello() -> Hello:
    """Shown on the hello page to prove the window can talk to the backend."""
    return Hello(message="Hello from Keptwise!", version=__version__)


# ---------- update check (Settings -> About and updates) ----------


class UpdatesBody(BaseModel):
    enabled: bool


def _with_install(status: dict[str, Any]) -> dict[str, Any]:
    # Whether "Update now" can work here (only in the installed app).
    return status | {"can_install": can_update_itself()}


@router.get("/updates")
def updates(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Called when the app opens: asks GitHub at most once a day, if switched on."""
    return _with_install(svc.updates.check())


@router.post("/updates/check")
def check_now(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _with_install(svc.updates.check(force=True))


@router.put("/updates")
def set_updates(body: UpdatesBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    return _with_install(svc.updates.set_enabled(body.enabled))


@router.post("/updates/install")
def install_update(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Download the newest version, check it, install it and restart (a job)."""
    if not can_update_itself():
        raise HTTPException(status_code=409, detail="Only the installed app can update itself. When running from source, pull the new code instead.")
    for job in svc.jobs.recent(20):
        if job["kind"] == "update" and job["status"] in ("queued", "running"):
            return job
    busy = [job["title"] for job in svc.jobs.recent(20) if job["status"] in ("running", "paused")]
    if busy:
        raise HTTPException(status_code=409, detail=f"Wait for “{busy[0]}” to finish (or cancel it), then update.")
    job_id = svc.runner.submit("update", "Update Keptwise")
    return svc.jobs.get(job_id) or {}
