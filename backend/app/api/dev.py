"""Developer page routes: database numbers and a fake background job."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.db.stats import database_stats
from app.services import AppServices, services

router = APIRouter(prefix="/api/dev")


@router.get("/stats")
def stats(svc: AppServices = Depends(services)) -> dict[str, Any]:
    result = database_stats(svc.db)
    result["data_dir"] = str(svc.paths.root)
    return result


@router.post("/fake-job")
def start_fake_job(svc: AppServices = Depends(services)) -> dict[str, Any]:
    job_id = svc.runner.submit("demo", "Fake 10-second job")
    return svc.jobs.get(job_id) or {}
