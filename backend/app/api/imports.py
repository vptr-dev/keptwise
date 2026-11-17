"""Import routes: receive dragged-in export files and start the import job.

How the window imports an export:
1. POST /api/imports              -> a new upload id, and which files to send
2. PUT  /api/imports/<id>/files?path=<name inside the drop>   (once per file;
   the request body is the file itself)
3. POST /api/imports/<id>/start   -> the "import" background job
Files are copied into the app's data folder only; nothing leaves this PC.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.importers import PLATFORM_NAMES, WANTED_EXTENSIONS, WANTED_FILE_NAMES
from app.importers.job import upload_folder
from app.services import AppServices, services

router = APIRouter(prefix="/api/imports")

# Characters Windows doesn't allow in file names.
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(10)), *(f"lpt{n}" for n in range(10))}
# Leave this much disk space free after copying (bytes).
SPARE_SPACE = 200 * 1024 * 1024


class StartBody(BaseModel):
    name: str | None = None  # what was dropped, e.g. "tiktok-export.zip"


def _folder(svc: AppServices, upload_id: str) -> Path:
    try:
        folder = upload_folder(svc.paths.imports, upload_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such upload.") from None
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="No such upload.")
    return folder


def safe_parts(raw: str) -> list[str]:
    """Split a dropped file's path into safe folder/file names.

    Refuses anything that could write outside the upload folder, like
    "..\\..\\Windows" or "C:\\something".
    """
    parts = [part for part in re.split(r"[\\/]+", raw) if part not in ("", ".")]
    problem = (
        not parts
        or len(parts) > 40
        or any(
            part == ".."
            or _BAD_CHARS.search(part)
            or part.endswith((" ", "."))
            or part.split(".")[0].lower() in _RESERVED
            or len(part) > 200
            for part in parts
        )
    )
    if problem:
        raise HTTPException(status_code=400, detail=f"Can't use the file name {raw!r}.")
    return parts


@router.post("")
def create_upload(svc: AppServices = Depends(services)) -> dict[str, Any]:
    upload_id = uuid.uuid4().hex
    upload_folder(svc.paths.imports, upload_id).mkdir(parents=True)
    return {
        "upload_id": upload_id,
        "wanted_names": WANTED_FILE_NAMES,
        "wanted_extensions": WANTED_EXTENSIONS,
    }


@router.put("/{upload_id}/files")
async def receive_file(
    upload_id: str, path: str, request: Request, svc: AppServices = Depends(services)
) -> dict[str, Any]:
    folder = _folder(svc, upload_id)
    parts = safe_parts(path)
    target = folder.joinpath(*parts)
    if not target.resolve().is_relative_to(folder.resolve()):
        raise HTTPException(status_code=400, detail=f"Can't use the file name {path!r}.")

    size = int(request.headers.get("content-length") or 0)
    if size and shutil.disk_usage(folder).free < size + SPARE_SPACE:
        raise HTTPException(
            status_code=400,
            detail="There isn't enough free disk space to copy this export. Free up some space and try again.",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as out:
        async for chunk in request.stream():
            out.write(chunk)
            written += len(chunk)
    return {"path": "/".join(parts), "bytes": written}


@router.post("/{upload_id}/start")
def start_import(
    upload_id: str, body: StartBody | None = None, svc: AppServices = Depends(services)
) -> dict[str, Any]:
    folder = _folder(svc, upload_id)
    if not any(file.is_file() for file in folder.rglob("*")):
        raise HTTPException(status_code=400, detail="No files arrived. Please drag the export in again.")
    name = (body.name if body else None) or "export"
    job_id = svc.runner.submit("import", f"Import {name}"[:120], {"upload_id": upload_id})
    return svc.jobs.get(job_id) or {}


@router.delete("/{upload_id}", status_code=204)
def discard_upload(upload_id: str, svc: AppServices = Depends(services)) -> Response:
    """Throw away a half-finished upload (e.g. the user cancelled it)."""
    try:
        folder = upload_folder(svc.paths.imports, upload_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such upload.") from None
    shutil.rmtree(folder, ignore_errors=True)
    return Response(status_code=204)


@router.get("/summary")
def library_summary(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """How many saved items the library has from each platform."""
    with svc.db.connect() as conn:
        rows = conn.execute("SELECT platform, COUNT(*) AS n FROM items GROUP BY platform").fetchall()
    counts = {row["platform"]: int(row["n"]) for row in rows}
    return {
        "total": sum(counts.values()),
        "platforms": [
            {"platform": key, "name": name, "count": counts.get(key, 0)}
            for key, name in PLATFORM_NAMES.items()
        ],
    }
