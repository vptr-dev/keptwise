"""Turning text into "meaning numbers" (embeddings) for the similar search.

We use fastembed with the small BAAI/bge-small-en-v1.5 model (about 67 MB,
runs on the processor, fully offline). The installed app ships the model
next to the program. When running from source it is downloaded once into
<data>\\models\\search\\ by our own downloader (progress bar, Cancel,
resume, and no Hugging Face hub package, so no telemetry).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.enrich.download import DownloadError, Opener, download_file, urllib_opener

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_FOLDER = "bge-small-en-v1.5"
REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
HUB = "https://huggingface.co"
WANTED_FILES = (
    "config.json",
    "model_optimized.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
APPROX_BYTES = 67_000_000
COMPLETE_MARKER = ".complete"
DIM = 384
# bge models find passages better when the question starts with this.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    name: str

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    """Scale every row to length 1, so a dot product is the cosine similarity."""
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors[None, :]
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return vectors / lengths


# ---------- finding the model on disk ----------


def bundled_model_dir() -> Path | None:
    """The copy shipped with the installed app (the build puts it there)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "models" / "search" / MODEL_FOLDER
    return None


def downloaded_model_dir(models_root: Path) -> Path:
    return models_root / "search" / MODEL_FOLDER


def find_model(models_root: Path) -> Path | None:
    """Where a complete copy of the model is, or None if there isn't one."""
    bundled = bundled_model_dir()
    if bundled and (bundled / "model_optimized.onnx").is_file():
        return bundled
    folder = downloaded_model_dir(models_root)
    if (folder / COMPLETE_MARKER).is_file():
        return folder
    return None


def download_search_model(
    models_root: Path,
    report: Callable[[int, int], None] | None = None,
    check: Callable[[], None] | None = None,
    opener: Opener = urllib_opener,
) -> Path:
    """Download the model if it isn't here yet. report(bytes_done, bytes_total)."""
    found = find_model(models_root)
    if found:
        return found
    response = opener(f"{HUB}/api/models/{REPO}/tree/main", {})
    try:
        entries: Any = json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
    files = [
        (str(entry["path"]), int(entry.get("size") or 0))
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "file" and entry.get("path") in WANTED_FILES
    ]
    if len(files) != len(WANTED_FILES):
        raise DownloadError("The search model's files weren't found on the download server.")
    folder = downloaded_model_dir(models_root)
    folder.mkdir(parents=True, exist_ok=True)
    total = sum(size for _, size in files)
    free = shutil.disk_usage(folder).free
    if free < total + 50_000_000:
        raise DownloadError(f"Not enough free disk space for the search model ({total / 1e6:.0f} MB).")
    done = 0

    def add(count: int) -> None:
        nonlocal done
        done += count
        if report:
            report(done, total)

    for name, size in files:
        download_file(f"{HUB}/{REPO}/resolve/main/{name}", folder / name, expected_size=size or None,
                      on_bytes=add, check=check, opener=opener)
    (folder / COMPLETE_MARKER).write_text("ok", encoding="utf-8")
    return folder


# ---------- the real embedder ----------


class FastEmbedder:
    """fastembed, loaded the first time it's needed (loading takes ~1 s)."""

    name = MODEL_NAME

    def __init__(self, model_dir: Path, threads: int | None = None) -> None:
        self.model_dir = model_dir
        # Leave most of the processor free for games and other apps.
        self.threads = threads or max(1, min(4, (os.cpu_count() or 2) // 2))
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                # Belt and braces: never let any library phone home.
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
                os.environ.setdefault("DO_NOT_TRACK", "1")
                from fastembed import TextEmbedding  # slow import, so done late

                self._model = TextEmbedding(
                    model_name=MODEL_NAME,
                    specific_model_path=str(self.model_dir),
                    cache_dir=str(self.model_dir.parent),
                    threads=self.threads,
                    cuda=False,
                )
            return self._model

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        vectors = list(self._load().embed(list(texts), batch_size=16))
        return normalize(np.vstack(vectors))

    def embed_query(self, text: str) -> np.ndarray:
        vectors = list(self._load().embed([QUERY_PREFIX + text]))
        return normalize(np.vstack(vectors))[0]
