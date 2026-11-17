"""The speech-to-text models the user can pick, and downloading them.

Models come from Hugging Face (the faster-whisper versions of OpenAI's
Whisper). They are downloaded once, on first use, into
<data>\\models\\whisper\\<model>\\. We download the files ourselves instead of
using the huggingface_hub package, so there's a progress bar, Cancel,
resume, and no telemetry.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.enrich.download import DownloadError, Opener, download_file, urllib_opener

HUB = "https://huggingface.co"
DEFAULT_MODEL = "small"
# Only these files are needed to run a model.
WANTED_FILES = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
    "vocabulary.json",
)
COMPLETE_MARKER = ".complete"
SPARE_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class SpeechModel:
    id: str
    label: str
    repo: str
    approx_bytes: int
    hint: str


MODELS: dict[str, SpeechModel] = {
    model.id: model
    for model in [
        SpeechModel("tiny", "Tiny", "Systran/faster-whisper-tiny", 75_000_000,
                    "Fastest, makes the most mistakes."),
        SpeechModel("base", "Base", "Systran/faster-whisper-base", 145_000_000,
                    "Fast, fine for clear speech."),
        SpeechModel("small", "Small (recommended)", "Systran/faster-whisper-small", 484_000_000,
                    "Good balance. About 6 seconds of speech per second on this kind of PC."),
        SpeechModel("medium", "Medium", "Systran/faster-whisper-medium", 1_530_000_000,
                    "More accurate, about 3 times slower than Small."),
        SpeechModel("large-v3-turbo", "Large (turbo)", "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                    1_620_000_000, "Most accurate. Slow without an NVIDIA graphics card."),
    ]
}


def model_folder(models_root: Path, model_id: str) -> Path:
    if model_id not in MODELS:
        raise ValueError(f"Unknown speech model {model_id!r}")
    return models_root / "whisper" / model_id


def is_downloaded(models_root: Path, model_id: str) -> bool:
    return (model_folder(models_root, model_id) / COMPLETE_MARKER).is_file()


def list_files(model: SpeechModel, opener: Opener) -> list[tuple[str, int]]:
    """Ask Hugging Face which files the model has, with their sizes."""
    response = opener(f"{HUB}/api/models/{model.repo}/tree/main", {})
    try:
        entries: Any = json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
    files = [
        (str(entry["path"]), int(entry.get("size") or 0))
        for entry in entries
        if isinstance(entry, dict) and entry.get("type") == "file" and entry.get("path") in WANTED_FILES
    ]
    if not any(name == "model.bin" for name, _ in files):
        raise DownloadError("The speech model's files weren't found on the download server.")
    return files


def download_model(
    models_root: Path,
    model_id: str,
    report: Callable[[int, int], None] | None = None,
    check: Callable[[], None] | None = None,
    opener: Opener = urllib_opener,
) -> Path:
    """Download a model if it isn't here yet. report(bytes_done, bytes_total)."""
    folder = model_folder(models_root, model_id)
    if is_downloaded(models_root, model_id):
        return folder
    model = MODELS[model_id]
    files = list_files(model, opener)
    total = sum(size for _, size in files)

    folder.mkdir(parents=True, exist_ok=True)
    missing = sum(size for name, size in files if not (folder / name).is_file())
    free = shutil.disk_usage(folder).free
    if free < missing + SPARE_BYTES:
        raise DownloadError(
            f"Not enough free disk space for the speech model: it needs about "
            f"{(missing + SPARE_BYTES) / 1e9:.1f} GB and {free / 1e9:.1f} GB is free."
        )

    done = 0

    def add(count: int) -> None:
        nonlocal done
        done += count
        if report:
            report(done, total)

    for name, size in files:
        download_file(
            f"{HUB}/{model.repo}/resolve/main/{name}",
            folder / name,
            expected_size=size or None,
            on_bytes=add,
            check=check,
            opener=opener,
        )
    (folder / COMPLETE_MARKER).write_text("ok", encoding="utf-8")
    return folder
