"""Everything the backend needs while running, created once at start-up.

API routes reach it with `services(request)`. Tests build their own with a
temporary data folder, a fake key store and a fake network, so they never
touch the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Request

from app import __version__

from app.ai.http import HttpClient
from app.ai.ollama_models import make_pull_handler
from app.ai.secrets import KeyringStore, KeyStore
from app.ai.service import AIService
from app.ai.sorting.job import make_notes_handler, make_sort_handler, make_tags_handler
from app.ai.sorting.settings import load as load_sorting
from app.db.connection import Database
from app.db.undo import UndoHistory
from app.db.settings_repo import SettingsRepo
from app.enrich.job import make_enrich_handler
from app.importers.job import make_import_handler, remove_old_uploads
from app.jobs.demo import run_demo_job
from app.jobs.events import EventHub
from app.jobs.repo import JobsRepo
from app.jobs.runner import Handler, JobContext, JobRunner
from app.paths import AppPaths
from app.search.embedder import Embedder
from app.search.service import SearchService
from app.updater import make_update_handler
from app.updates import UpdateChecker


@dataclass
class AppServices:
    paths: AppPaths
    db: Database
    settings: SettingsRepo
    hub: EventHub
    jobs: JobsRepo
    runner: JobRunner
    ai: AIService
    search: SearchService
    updates: UpdateChecker
    # Extra services added by later parts of the app.
    extras: dict[str, Any] = field(default_factory=dict)

    def shutdown(self) -> None:
        self.runner.shutdown()
        self.hub.close()


def notes_after(handler: Handler, db: Database, settings: SettingsRepo, ai: AIService, runner: JobRunner,
                jobs: JobsRepo) -> Handler:
    """Wrap the transcripts job: when it ends and the user switched on
    "write notes by themselves", start the notes job for everything that now
    has a transcript. Only with a local AI (a cloud one costs money, so it
    waits to be asked), only when it's ready, and never two notes jobs at once."""

    def run(ctx: JobContext) -> dict[str, Any] | None:
        try:
            return handler(ctx)
        finally:
            try:
                if load_sorting(settings).auto_notes and not ai.is_cloud():
                    ai.check_ready()
                    busy = any(job["kind"] == "notes" and job["status"] in ("queued", "running", "paused")
                               for job in jobs.recent(20))
                    with db.connect() as conn:
                        ids = [int(row["id"]) for row in conn.execute(
                            "SELECT id FROM items WHERE status = 'enriched' AND deleted_at IS NULL "
                            "ORDER BY saved_at DESC, id DESC"
                        )]
                    if ids and not busy:
                        runner.submit("notes", f"AI notes for {len(ids):,} video{'s' if len(ids) != 1 else ''}",
                                      {"item_ids": ids})
            except Exception:  # noqa: BLE001 - never spoil the job that just ran
                pass

    return run


def build_services(
    data_dir: Path,
    keys: KeyStore | None = None,
    http: HttpClient | None = None,
    embedder: Embedder | None = None,
) -> AppServices:
    paths = AppPaths(data_dir).create()
    db = Database(paths.database)
    UndoHistory(db)  # db.undo: records what requests change, for Undo and Redo
    settings = SettingsRepo(db)
    hub = EventHub()
    jobs = JobsRepo(db)
    runner = JobRunner(jobs, hub)
    http = http or HttpClient()
    ai = AIService(settings, keys or KeyringStore(), http)

    # Tests pass a fake embedder; the real app finds the fastembed model itself.
    search = SearchService(db, paths.models, runner, jobs, embedder=embedder)

    runner.register("demo", run_demo_job)
    runner.register("ollama_pull", make_pull_handler(http))
    runner.register("import", make_import_handler(db, paths.imports))
    runner.register("enrich", notes_after(search.after(make_enrich_handler(db, paths, settings)), db, settings, ai, runner, jobs))
    runner.register("notes", search.after(make_notes_handler(db, settings, ai)))
    runner.register("sort", make_sort_handler(db, settings, ai))
    runner.register("tags", make_tags_handler(db, settings, ai))
    # One-click update. The launcher puts "quit_app" (closes the window) in extras.
    extras: dict[str, Any] = {}
    runner.register("update", make_update_handler(http.get_json, __version__, lambda: extras.get("quit_app")))
    remove_old_uploads(paths.imports)

    return AppServices(
        paths=paths,
        db=db,
        settings=settings,
        hub=hub,
        jobs=jobs,
        runner=runner,
        ai=ai,
        search=search,
        updates=UpdateChecker(settings, http),
        extras=extras,
    )


def services(request: Request) -> AppServices:
    """FastAPI helper: the AppServices of the running app."""
    return request.app.state.services
