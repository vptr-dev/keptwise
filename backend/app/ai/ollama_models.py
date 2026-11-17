"""Checking Ollama and downloading its models from inside the app.

The download runs as a background job through Ollama's /api/pull. If it
is cancelled, Ollama keeps the parts it already has, so the next
download carries on from there.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.ai.base import AIError
from app.ai.http import HttpClient, HttpError
from app.ai.providers.ollama import OllamaProvider
from app.jobs.runner import JobContext

OLLAMA_DOWNLOAD_PAGE = "https://ollama.com/download"
DEFAULT_MODEL = "gemma4:12b"

# Models the picker suggests. Sizes are the download size in GB (approx.).
RECOMMENDED: list[dict[str, Any]] = [
    {
        "name": "gemma4:12b",
        "label": "Gemma 4 12B",
        "size_gb": 8.0,
        "note": "Recommended. Best results; runs well with 8 GB+ graphics memory or 16 GB+ RAM.",
    },
    {
        "name": "gemma4:e4b",
        "label": "Gemma 4 E4B",
        "size_gb": 6.6,
        "note": "Lighter and faster, for older or weaker PCs.",
    },
]


def models_folder() -> Path:
    """Where Ollama keeps downloaded models (OLLAMA_MODELS, or ~/.ollama/models)."""
    custom = os.environ.get("OLLAMA_MODELS")
    return Path(custom) if custom else Path.home() / ".ollama" / "models"


def free_disk_bytes(folder: Path) -> int | None:
    """Free space on the drive holding folder (the folder may not exist yet)."""
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def ollama_status(http: HttpClient, base_url: str) -> dict[str, Any]:
    """Is Ollama running, which version, and which models are downloaded."""
    provider = OllamaProvider(http, model="", base_url=base_url)
    status: dict[str, Any] = {
        "base_url": provider.base_url,
        "running": False,
        "version": None,
        "installed": [],
        "error": None,
        "download_page": OLLAMA_DOWNLOAD_PAGE,
        "default_model": DEFAULT_MODEL,
        "free_bytes": free_disk_bytes(models_folder()),
    }
    try:
        status["version"] = provider.version()
        status["installed"] = provider.list_models()
        status["running"] = True
    except AIError as error:
        status["error"] = str(error)
    installed = set(status["installed"])
    status["recommended"] = [
        {**model, "installed": _is_installed(model["name"], installed)} for model in RECOMMENDED
    ]
    return status


def _is_installed(name: str, installed: set[str]) -> bool:
    # "gemma4" and "gemma4:latest" are the same model.
    return name in installed or (":" not in name and f"{name}:latest" in installed)


def _gb(n: int) -> str:
    return f"{n / 1_000_000_000:.1f} GB"


def expected_bytes(model: str) -> int | None:
    """Download size of a recommended model, or None if we don't know it."""
    for rec in RECOMMENDED:
        if rec["name"] == model:
            return int(rec["size_gb"] * 1_000_000_000)
    return None


def check_free_space(model: str, free: int | None) -> None:
    """Refuse to start a download that can't fit on the disk."""
    need = expected_bytes(model)
    if need and free is not None and free < need * 1.1:
        raise AIError(
            f"Not enough free disk space for {model}: it needs about {_gb(need)} "
            f"and only {_gb(free)} is free. Free up some space, then try again.",
            "no_space",
        )


def make_pull_handler(http: HttpClient):  # type: ignore[no-untyped-def]
    """Build the job handler that downloads params['model'] via Ollama."""

    def pull(ctx: JobContext) -> dict[str, Any]:
        model = str(ctx.params["model"])
        base_url = str(ctx.params.get("base_url") or "http://localhost:11434").rstrip("/")
        # Ollama reports the model's files (layers) one at a time. Knowing the
        # full size up front keeps the bar from jumping back when a big layer starts.
        expected = int(ctx.params.get("expected_bytes") or 0)
        layers: dict[str, tuple[int, int]] = {}
        ctx.progress(0, expected, f"Starting download of {model}…")
        try:
            lines = http.post_json_lines(
                f"{base_url}/api/pull", {"model": model, "stream": True}, timeout=60
            )
            for line in lines:
                ctx.check()  # Cancel stops here; Ollama keeps the finished parts.
                if line.get("error"):
                    raise AIError(f"Ollama couldn't download {model}: {line['error']}")
                status = str(line.get("status", ""))
                digest = line.get("digest")
                if digest and line.get("total"):
                    layers[digest] = (int(line.get("completed", 0)), int(line["total"]))
                done = sum(c for c, _ in layers.values())
                total = max(sum(t for _, t in layers.values()), expected)
                if total and digest:
                    ctx.progress(done, total, f"Downloading {model}: {_gb(done)} of {_gb(total)}")
                else:
                    # e.g. "pulling manifest", "verifying sha256 digest"
                    ctx.progress(done, total, f"{model}: {status}")
                if status == "success":
                    break
        except HttpError as error:
            if error.status is None:
                raise AIError(
                    "Couldn't reach Ollama. Make sure it's installed and running, "
                    f"or run this in PowerShell: ollama pull {model}"
                ) from error
            raise AIError(f"Ollama refused the download ({error.status}): {error.body[:200]}") from error
        total = sum(t for _, t in layers.values())
        ctx.progress(total, total)
        return {"message": f"{model} is downloaded and ready", "model": model}

    return pull
