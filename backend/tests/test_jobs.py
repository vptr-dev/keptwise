"""Tests for background jobs: progress, pause/resume, cancel, failures, events."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from app.jobs.events import EventHub
from app.jobs.runner import JobContext
from app.services import AppServices


def wait_for_status(svc: AppServices, job_id: int, *statuses: str, timeout: float = 5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    job: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        job = svc.jobs.get(job_id)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} never reached {statuses}; last seen: {job}")


def test_job_runs_to_done_with_progress(svc: AppServices) -> None:
    def handler(ctx: JobContext) -> dict[str, Any]:
        for step in range(1, 4):
            ctx.check()
            ctx.progress(step, 3, f"step {step}")
        return {"message": "all good", "count": 3}

    svc.runner.register("count", handler)
    svc.runner.start()
    job_id = svc.runner.submit("count", "Count to 3")
    job = wait_for_status(svc, job_id, "done")
    assert job["progress"] == 3 and job["total"] == 3
    assert job["message"] == "all good"
    assert job["result"] == {"message": "all good", "count": 3}


def test_failure_is_recorded_not_raised(svc: AppServices) -> None:
    def handler(ctx: JobContext) -> None:
        raise RuntimeError("disk is full")

    svc.runner.register("broken", handler)
    svc.runner.start()
    job = wait_for_status(svc, svc.runner.submit("broken", "Broken"), "failed")
    assert job["error"] == "disk is full"


def test_pause_resume_and_cancel(svc: AppServices) -> None:
    started = threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        for step in range(1000):
            ctx.check()
            ctx.progress(step, 1000)
            time.sleep(0.01)

    svc.runner.register("slow", handler)
    svc.runner.start()
    job_id = svc.runner.submit("slow", "Slow")
    assert started.wait(5)

    svc.runner.pause(job_id)
    wait_for_status(svc, job_id, "paused")
    svc.runner.resume(job_id)
    wait_for_status(svc, job_id, "running")
    svc.runner.cancel(job_id)
    job = wait_for_status(svc, job_id, "cancelled")
    assert job["finished_at"]


def test_interrupted_jobs_can_be_resumed(svc: AppServices) -> None:
    runs: list[int] = []

    def handler(ctx: JobContext) -> None:
        runs.append(ctx.job_id)

    svc.runner.register("again", handler)
    # Pretend the app closed while this job was running.
    job_id = svc.jobs.create("again", "Again", {})
    svc.jobs.update(job_id, status="running")
    svc.runner.start()  # start-up marks it interrupted
    assert svc.jobs.get(job_id)["status"] == "interrupted"  # type: ignore[index]

    svc.runner.resume(job_id)
    wait_for_status(svc, job_id, "done")
    assert runs == [job_id]


def test_event_hub_wait_returns_new_events() -> None:
    hub = EventHub()
    hub.publish("job", {"id": 1})
    hub.publish("job", {"id": 2})
    assert [event.data["id"] for event in hub.wait_for(1, timeout=0)] == [2]
    # Nothing new: waits, then returns empty.
    assert hub.wait_for(2, timeout=0.05) == []


def test_api_fake_job_and_event_stream(api: TestClient, svc: AppServices) -> None:
    svc.runner.register("demo", lambda ctx: {"message": "quick"})  # make it instant
    response = api.post("/api/dev/fake-job")
    assert response.status_code == 200
    job_id = response.json()["id"]
    # Wait for the announcement, not just the database: the runner saves
    # "done" a moment before it posts it to the event stream.
    deadline = time.monotonic() + 5
    while not any(
        event.data.get("id") == job_id and event.data.get("status") == "done"
        for event in svc.hub.wait_for(0, timeout=0.05)
    ):
        assert time.monotonic() < deadline, "the done event never arrived"
        time.sleep(0.01)  # give the job thread room to post it

    with api.stream("GET", "/api/events?after=0&once=true") as stream:
        body = "".join(stream.iter_text())
    assert "event: ready" in body
    job_events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ") and '"kind"' in line
    ]
    assert job_events[-1]["id"] == job_id
    assert job_events[-1]["status"] == "done"


def test_api_job_controls(api: TestClient, svc: AppServices) -> None:
    gate = threading.Event()

    def handler(ctx: JobContext) -> None:
        while not gate.is_set():
            ctx.check()
            time.sleep(0.01)

    svc.runner.register("demo", handler)
    job_id = api.post("/api/dev/fake-job").json()["id"]
    wait_for_status(svc, job_id, "running")
    assert api.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    wait_for_status(svc, job_id, "cancelled")
    assert any(job["id"] == job_id for job in api.get("/api/jobs").json())
    assert api.post("/api/jobs/9999/pause").status_code == 404


def test_api_dev_stats(api: TestClient) -> None:
    stats = api.get("/api/dev/stats").json()
    assert stats["tables"]["items"] == 0
    assert stats["data_dir"].endswith("data")
