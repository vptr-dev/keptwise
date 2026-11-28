"""Runs long tasks (downloads, transcription, AI calls) in the background.

How a job works:
1. Code calls runner.submit("enrich", "Enrich 50 items", {...}).
2. A worker thread picks it up and calls the handler registered for
   "enrich", passing a JobContext.
3. The handler reports progress with ctx.progress(...) and calls
   ctx.check() often. check() is where Pause and Cancel take effect.
4. Every change is saved to the database and posted to the EventHub, so
   the UI shows it live.

Handlers must be safe to run again: after Resume (or an app restart) the
same job runs from the start, and the handler skips work already done.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.jobs.events import EventHub
from app.jobs.repo import JobsRepo

Handler = Callable[["JobContext"], dict[str, Any] | None]

# Don't save/announce progress more often than this (seconds).
PROGRESS_INTERVAL = 0.2


class JobCancelled(Exception):
    """Raised inside a handler by ctx.check() when the user cancels."""


class JobsBusy(Exception):
    """A job is queued or still using the library."""


class _Control:
    """Pause and cancel switches for one job."""

    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.running = threading.Event()  # cleared = paused
        self.running.set()


class JobContext:
    def __init__(self, runner: "JobRunner", job_id: int, params: dict[str, Any]) -> None:
        self._runner = runner
        self.job_id = job_id
        self.params = params
        self._control = runner._control_for(job_id)
        self._last_report = 0.0
        self.done = 0
        self.total = 0

    def progress(
        self, done: int, total: int | None = None, message: str | None = None, force: bool = False
    ) -> None:
        """Report how far the job is, e.g. progress(3, 10, "Transcribing video 3").

        Quick updates in a row are thinned out. Pass force=True for a new step
        (like "Transcribing video 3"), so it is always shown even if it comes
        right after the previous update.
        """
        self.done = done
        if total is not None:
            self.total = total
        now = time.monotonic()
        is_last = self.total and done >= self.total
        if now - self._last_report < PROGRESS_INTERVAL and not is_last and not force:
            return
        self._last_report = now
        fields: dict[str, Any] = {"progress": done, "total": self.total}
        if message is not None:
            fields["message"] = message
        self._runner._update(self.job_id, **fields)

    def save_params(self, **fields: Any) -> None:
        """Persist a checkpoint for a resumed job."""
        self.params.update(fields)
        self._runner._repo.update(self.job_id, params_json=json.dumps(self.params))

    def check(self) -> None:
        """Stop here if the user pressed Cancel; wait here while paused."""
        control = self._control
        if control.cancel.is_set():
            raise JobCancelled
        if not control.running.is_set():
            self._runner._update(self.job_id, status="paused")
            while not control.running.wait(timeout=0.5):
                if control.cancel.is_set():
                    raise JobCancelled
            if control.cancel.is_set():
                raise JobCancelled
            self._runner._update(self.job_id, status="running")

    @property
    def cancelled(self) -> bool:
        return self._control.cancel.is_set()


class JobRunner:
    def __init__(self, repo: JobsRepo, hub: EventHub, workers: int = 2) -> None:
        self._repo = repo
        self._hub = hub
        self._handlers: dict[str, Handler] = {}
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._controls: dict[int, _Control] = {}
        self._lock = threading.Lock()
        self._start_gate = threading.RLock()
        self._working: dict[int, dict[str, Any]] = {}
        self._workers = workers
        self._threads: list[threading.Thread] = []

    # ---------- setting up ----------

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def start(self) -> None:
        """Start the worker threads. Jobs cut off by a restart become 'interrupted'."""
        if self._threads:
            return
        for job_id in self._repo.mark_interrupted():
            self._announce(job_id)
        for number in range(self._workers):
            thread = threading.Thread(
                target=self._work, name=f"job-worker-{number}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def shutdown(self) -> None:
        """Cancel running jobs and stop the workers (used when the app closes)."""
        with self._lock:
            for control in self._controls.values():
                control.cancel.set()
                control.running.set()
        for _ in self._threads:
            self._queue.put(None)

    # ---------- what the API calls ----------

    def submit(self, kind: str, title: str, params: dict[str, Any] | None = None) -> int:
        if kind not in self._handlers:
            raise ValueError(f"No handler for job kind {kind!r}")
        with self._start_gate:
            job_id = self._repo.create(kind, title, params or {})
            self._announce(job_id)
            self._queue.put(job_id)
            return job_id

    def pause(self, job_id: int) -> None:
        self._control_for(job_id).running.clear()
        job = self._repo.get(job_id)
        if job and job["status"] == "queued":
            self._update(job_id, status="paused")

    def resume(self, job_id: int) -> None:
        with self._start_gate:
            job = self._repo.get(job_id)
            if job is None:
                raise KeyError(job_id)
            control = self._control_for(job_id)
            control.running.set()
            if job["status"] in ("interrupted", "failed", "cancelled"):
                # Run it again from the start; the handler skips finished work.
                control.cancel.clear()
                self._update(job_id, status="queued", error=None, finished_at=None,
                             message="Resuming…", notice_dismissed=0)
                self._queue.put(job_id)

    @contextmanager
    def maintenance(self) -> Iterator[None]:
        """Keep new jobs out while an idle library is being cleared."""
        with self._start_gate:
            running = next(iter(self._working.values()), None)
            title = running["title"] if running is not None else self._repo.active_title()
            if title is not None:
                raise JobsBusy(f"“{title}” is still active. Finish or cancel it first.")
            yield

    def cancel(self, job_id: int) -> None:
        control = self._control_for(job_id)
        control.cancel.set()
        control.running.set()  # wake it if paused, so it can stop
        with self._start_gate:
            job = self._repo.get(job_id)
            if job and job_id not in self._working and job["status"] in ("queued", "paused", "interrupted"):
                self._finish(job_id, "cancelled", message="Cancelled")

    # ---------- inside the worker threads ----------

    def _control_for(self, job_id: int) -> _Control:
        with self._lock:
            return self._controls.setdefault(job_id, _Control())

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            self._run(job_id)

    def _run(self, job_id: int) -> None:
        with self._start_gate:
            job = self._repo.get(job_id)
            if job is None or job_id in self._working or job["status"] not in ("queued", "paused"):
                return
            self._working[job_id] = job
        try:
            self._execute(job_id, job)
        finally:
            with self._start_gate:
                if self._working.get(job_id) is job:
                    self._working.pop(job_id)

    def _execute(self, job_id: int, job: dict[str, Any]) -> None:
        handler = self._handlers.get(job["kind"])
        if handler is None:
            self._finish(job_id, "failed", error=f"Unknown job kind {job['kind']!r}")
            return
        ctx = JobContext(self, job_id, job["params"])
        self._update(job_id, status="running")
        try:
            ctx.check()
            result = handler(ctx)
        except JobCancelled:
            self._finish(job_id, "cancelled", message="Cancelled")
        except Exception as error:  # noqa: BLE001 - one job must never crash the app
            traceback.print_exc()
            self._finish(job_id, "failed", error=str(error) or type(error).__name__)
        else:
            self._update(job_id, progress=ctx.total or ctx.done, total=ctx.total)
            self._finish(
                job_id,
                "done",
                message=(result or {}).get("message", "Done"),
                result_json=json.dumps(result or {}),
            )

    def _finish(self, job_id: int, status: str, **fields: Any) -> None:
        with self._start_gate:
            self._working.pop(job_id, None)
            self._update(
                job_id,
                status=status,
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **fields,
            )

    def _update(self, job_id: int, **fields: Any) -> None:
        self._repo.update(job_id, **fields)
        self._announce(job_id)

    def _announce(self, job_id: int) -> None:
        job = self._repo.get(job_id)
        if job is not None:
            self._hub.publish("job", job)
