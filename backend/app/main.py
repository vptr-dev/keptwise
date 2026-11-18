"""Builds the backend web app: API routes plus the app's pages.

The desktop launcher (desktop/launcher.py) calls create_app() and runs the
result on a random free port on 127.0.0.1, so only this computer can reach it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.ai.base import AIError
from app.api import (
    ai,
    assistant,
    dev,
    enrich,
    imports,
    jobs,
    library,
    organize,
    plans,
    search,
    session,
    sorting,
    storage,
    system,
    undo,
)
from app.db.undo import UNDO_STEP_HEADER, label_for, recording, should_record
from app.frontend import mount_frontend
from app.paths import default_data_dir
from app.services import AppServices, build_services

# Routers that need the session token, in the order they're added.
PROTECTED_ROUTERS = [
    system.router, jobs.router, dev.router, ai.router, imports.router, enrich.router, sorting.router,
    search.router, library.router, storage.router, organize.router, plans.router, assistant.router,
    undo.router,
]


def _ai_error(_request: Request, error: Exception) -> JSONResponse:
    """AI problems become a clear message (and a code the UI can act on)."""
    code = getattr(error, "code", "ai_error")
    return JSONResponse(status_code=400, content={"detail": str(error), "code": code})


def create_app(
    session_token: str,
    static_dir: Path,
    data_dir: Path | None = None,
    app_services: AppServices | None = None,
) -> FastAPI:
    """Create the backend app.

    session_token: random secret made by the launcher at every start. Every
        /api request must prove it knows it (see app/api/session.py).
    static_dir: folder with the built frontend (index.html and assets).
    data_dir: where the user's data lives (default: %APPDATA%\\Keptwise).
    app_services: ready-made services (tests use this to swap parts out).
    """
    app = FastAPI(
        title="Keptwise",
        version=__version__,
        # No auto-generated API docs pages: they load files from the internet.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        # Privacy: switch off FastAPI's built-in OpenTelemetry completely,
        # so nothing is ever measured or sent anywhere.
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "auto_configure": False,
        },
    )
    app.state.session_token = session_token
    svc = app_services or build_services(data_dir or default_data_dir())
    svc.runner.start()
    app.state.services = svc
    # Videos transcribed while the app was closed (or cut off) get ready for
    # similar search in the background. Only if the model is already here.
    svc.search.ensure_index()
    app.add_exception_handler(AIError, _ai_error)

    @app.middleware("http")
    async def record_for_undo(request: Request, call_next: Any) -> Any:
        """Each change made through the app becomes one Undo step."""
        history = svc.db.undo
        if history is None or not should_record(request.method, request.url.path):
            return await call_next(request)
        # The AI's actions in one answer share a step (app/search/agent.py).
        given = request.headers.get(UNDO_STEP_HEADER, "")
        step = int(given) if given.isdigit() else history.new_step()
        token = recording.set(step)
        try:
            response = await call_next(request)
        finally:
            recording.reset(token)
        if not given:
            await run_in_threadpool(history.finish, step, label_for(request.method, request.url.path))
        return response

    # Open to anyone on this PC: only says "the server is up".
    app.include_router(system.public_router)
    # Turns the launcher's one-time link into a session cookie.
    app.include_router(session.router)
    # Everything else under /api needs the session token.
    for router in PROTECTED_ROUTERS:
        app.include_router(router, dependencies=[Depends(session.require_session)])

    # Must come last: it answers every path the routes above don't.
    mount_frontend(app, static_dir)
    return app
