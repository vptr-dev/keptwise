"""AI settings routes: pick provider and model, API keys, test, Ollama downloads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.base import AIError
from app.ai.ollama_models import (
    check_free_space,
    expected_bytes,
    free_disk_bytes,
    models_folder,
    ollama_status,
)
from app.ai.service import SETUP_DONE
from app.services import AppServices, services

router = APIRouter(prefix="/api/ai")


class CurrentChoice(BaseModel):
    provider: str


class ProviderChanges(BaseModel):
    model: str | None = None
    base_url: str | None = None


class KeyBody(BaseModel):
    key: str


class PullBody(BaseModel):
    model: str


class SetupBody(BaseModel):
    done: bool = True


@router.get("")
def overview(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return svc.ai.overview()


@router.put("/current")
def set_current(body: CurrentChoice, svc: AppServices = Depends(services)) -> dict[str, Any]:
    svc.ai.set_current(body.provider)
    return svc.ai.overview()


@router.put("/providers/{provider_id}")
def change_provider(
    provider_id: str, body: ProviderChanges, svc: AppServices = Depends(services)
) -> dict[str, Any]:
    if body.model is not None:
        svc.ai.set_model(provider_id, body.model)
    if body.base_url is not None:
        svc.ai.set_base_url(provider_id, body.base_url)
    return svc.ai.overview()


@router.put("/providers/{provider_id}/key")
def save_key(provider_id: str, body: KeyBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    svc.ai.save_key(provider_id, body.key)
    return svc.ai.overview()


@router.delete("/providers/{provider_id}/key")
def remove_key(provider_id: str, svc: AppServices = Depends(services)) -> dict[str, Any]:
    svc.ai.remove_key(provider_id)
    return svc.ai.overview()


@router.get("/providers/{provider_id}/models")
def list_models(provider_id: str, svc: AppServices = Depends(services)) -> dict[str, Any]:
    models = svc.ai.list_models(provider_id)
    return {"models": models, "model": svc.ai.model_for(provider_id)}


@router.post("/providers/{provider_id}/test")
def test_connection(provider_id: str, svc: AppServices = Depends(services)) -> dict[str, Any]:
    try:
        return {"ok": True, "message": svc.ai.test_connection(provider_id)}
    except AIError as error:
        return {"ok": False, "message": str(error), "code": error.code}


@router.get("/ready")
def ready(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Can AI jobs run right now? If not, why (the UI shows a fix)."""
    try:
        svc.ai.check_ready()
    except AIError as error:
        return {"ready": False, "message": str(error), "code": error.code}
    return {"ready": True, "message": "Ready", "code": None}


@router.post("/setup-done")
def setup_done(body: SetupBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    svc.settings.set(SETUP_DONE, body.done)
    return svc.ai.overview()


@router.get("/ollama")
def ollama(svc: AppServices = Depends(services)) -> dict[str, Any]:
    return ollama_status(svc.ai.http, svc.ai.base_url_for("ollama"))


@router.post("/ollama/pull")
def pull_model(body: PullBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    model = body.model.strip()
    if not model:
        raise AIError("Type a model name, for example gemma4:12b.")
    earlier = [
        job
        for job in svc.jobs.recent(20)
        if job["kind"] == "ollama_pull" and job["params"].get("model") == model
    ]
    # Already downloading this model? Show that job instead of starting another.
    for job in earlier:
        if job["status"] in ("queued", "running", "paused"):
            return job
    check_free_space(model, free_disk_bytes(models_folder()))
    # Downloads cut off by an app restart are replaced by this new one
    # (Ollama kept their finished parts, so nothing is downloaded twice).
    for job in earlier:
        if job["status"] == "interrupted":
            svc.runner.cancel(job["id"])
    job_id = svc.runner.submit(
        "ollama_pull",
        f"Download {model}",
        {
            "model": model,
            "base_url": svc.ai.base_url_for("ollama"),
            "expected_bytes": expected_bytes(model),
        },
    )
    return svc.jobs.get(job_id) or {}
