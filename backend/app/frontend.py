"""Serves the built frontend (the app's pages) from the backend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Shown instead of the app when the frontend hasn't been built yet.
NOT_BUILT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Keptwise</title></head>
<body style="font-family: sans-serif; margin: 3rem;">
<h1>Keptwise</h1>
<p>The app's pages haven't been built yet.</p>
<p>Close this window and run <code>.\\scripts\\dev.ps1</code> from the project folder.</p>
</body></html>"""


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve files from static_dir at "/", or a help page if it's missing."""
    if (static_dir / "index.html").is_file():
        # html=True makes "/" return index.html.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
        return

    @app.get("/", include_in_schema=False)
    def not_built() -> HTMLResponse:
        return HTMLResponse(NOT_BUILT_PAGE)
