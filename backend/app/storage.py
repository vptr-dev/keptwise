"""What takes up disk space, and freeing it (Settings -> Storage).

Everything listed here can be deleted safely: the app keeps working, and
whatever needs a deleted model asks to download it again (or downloads it
by itself next time). The saves, notes and transcripts are never listed:
they live in the database and only the uninstaller removes them.
"""

from __future__ import annotations

import gc
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.ai.http import HttpClient, HttpError
from app.enrich.speech_models import MODELS as SPEECH_MODELS
from app.search.embedder import downloaded_model_dir

# Jobs that read the models or the sound files. Nothing is deleted while one runs.
BUSY_JOB_KINDS = {"enrich", "notes", "sort", "search_index", "ollama_pull"}
BUSY_STATUSES = {"queued", "running", "paused"}


class StorageError(Exception):
    """A plain-English reason something couldn't be deleted."""


@dataclass
class StorageEntry:
    id: str  # e.g. "speech:small", "ollama:gemma4:12b", "audio"
    group: str  # "AI models", "Speech to text", "Search", "Files"
    label: str
    bytes: int
    note: str  # what happens if it's deleted
    can_delete: bool = True
    in_use: bool = False  # the model the app is set to use


def folder_bytes(folder: Path) -> int:
    """Total size of every file inside a folder (0 if it doesn't exist)."""
    if not folder.exists():
        return 0
    total = 0
    for file in folder.rglob("*"):
        try:
            if file.is_file():
                total += file.stat().st_size
        except OSError:
            pass  # a file vanished or is locked; skip it
    return total


def _clear_folder(folder: Path) -> None:
    """Delete everything inside a folder but keep the folder itself."""
    if not folder.exists():
        return
    for child in folder.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


# ---------- what's there ----------


def local_entries(models_root: Path, audio: Path, imports: Path, thumbnails: Path, database: Path,
                  chosen_speech_model: str) -> list[StorageEntry]:
    """Models and files inside the app's own data folder."""
    entries: list[StorageEntry] = []
    whisper_root = models_root / "whisper"
    if whisper_root.exists():
        for folder in sorted(p for p in whisper_root.iterdir() if p.is_dir()):
            info = SPEECH_MODELS.get(folder.name)
            label = info.label.replace(" (recommended)", "") if info else folder.name
            in_use = folder.name == chosen_speech_model
            entries.append(StorageEntry(
                id=f"speech:{folder.name}",
                group="Speech to text",
                label=f"Speech model: {label}",
                bytes=folder_bytes(folder),
                note=("Transcripts are paused until it's downloaded again. The next transcript job downloads it by itself."
                      if in_use else "Not the model you use now, so nothing changes."),
                in_use=in_use,
            ))
    search_folder = downloaded_model_dir(models_root)
    if search_folder.exists():
        entries.append(StorageEntry(
            id="search-model",
            group="Search",
            label="Similar-ideas search model",
            bytes=folder_bytes(search_folder),
            note="Word search keeps working. \"Similar ideas\" stops until you turn it on again on the Search screen.",
        ))
    entries.append(StorageEntry(
        id="audio", group="Files", label="Downloaded video sound", bytes=folder_bytes(audio),
        note="Only kept while a transcript is being made. Safe to clear.",
    ))
    entries.append(StorageEntry(
        id="imports", group="Files", label="Leftover export copies", bytes=folder_bytes(imports),
        note="Copies of export files from imports that didn't finish. Safe to clear.",
    ))
    entries.append(StorageEntry(
        id="thumbnails", group="Files", label="Video pictures", bytes=folder_bytes(thumbnails),
        note="The pictures on your Library cards. Kept so the Library looks right.", can_delete=False,
    ))
    size = database.stat().st_size if database.exists() else 0
    entries.append(StorageEntry(
        id="database", group="Files", label="Your saves, notes and transcripts", bytes=size,
        note="Everything you've imported and written. Never deleted from here.", can_delete=False,
    ))
    return entries


def ollama_entries(http: HttpClient, base_url: str, chosen: str | None) -> list[StorageEntry]:
    """AI models downloaded in Ollama (empty if Ollama isn't running)."""
    try:
        data = http.get_json(f"{base_url.rstrip('/')}/api/tags", timeout=5)
    except HttpError:
        return []
    entries = []
    for model in data.get("models", []):
        name = str(model.get("name") or model.get("model") or "")
        if not name:
            continue
        in_use = chosen is not None and name in (chosen, f"{chosen}:latest")
        entries.append(StorageEntry(
            id=f"ollama:{name}",
            group="AI models",
            label=name,
            bytes=int(model.get("size") or 0),
            note=("Your current AI model. Notes, sorting and chat stop until you download it again in Settings -> AI."
                  if in_use else "Not the model you use now. Other apps that use Ollama can't use it either once deleted."),
            in_use=in_use,
        ))
    return entries


def as_dicts(entries: list[StorageEntry]) -> list[dict[str, Any]]:
    return [asdict(e) for e in entries]


# ---------- deleting ----------


def delete_local(entry_id: str, models_root: Path, audio: Path, imports: Path) -> None:
    """Delete one of the app's own models or file groups."""
    try:
        if entry_id.startswith("speech:"):
            name = entry_id.split(":", 1)[1]
            folder = (models_root / "whisper" / name).resolve()
            if folder.parent != (models_root / "whisper").resolve() or not folder.is_dir():
                raise StorageError("That speech model isn't downloaded.")
            gc.collect()  # let go of a model that was loaded earlier
            shutil.rmtree(folder)
        elif entry_id == "search-model":
            shutil.rmtree(downloaded_model_dir(models_root), ignore_errors=False)
        elif entry_id == "audio":
            _clear_folder(audio)
        elif entry_id == "imports":
            _clear_folder(imports)
        else:
            raise StorageError("That can't be deleted from here.")
    except FileNotFoundError:
        pass  # already gone
    except PermissionError as error:
        raise StorageError(
            "Windows wouldn't let go of a file because it's still in use. Close and reopen Keptwise, then try again."
        ) from error


def delete_ollama(http: HttpClient, base_url: str, name: str) -> None:
    """Ask Ollama to delete one of its downloaded models."""
    try:
        http.delete_json(f"{base_url.rstrip('/')}/api/delete", {"model": name}, timeout=30)
    except HttpError as error:
        if error.status == 404:
            return  # already gone
        raise StorageError(f"Ollama couldn't delete {name}. Is Ollama running? ({error})") from error


# ---------- clearing your own data (Settings -> Storage) ----------

# Everything the user saved or made. Settings and the spaces themselves stay.
SAVES_TABLES = (
    "chat_messages", "chats", "plan_tasks", "plan_items", "plans", "item_tags", "tags", "item_collections",
    "collections", "platform_links", "removed_links", "search_passages", "search_indexed", "search_fts",
    "embeddings", "ai_results", "transcripts", "items", "jobs",
)


def clear_backups(backups: Path) -> int:
    """Delete the database copies kept before updates. Returns how many."""
    if not backups.is_dir():
        return 0
    gone = 0
    for copy in backups.glob("*.db"):
        try:
            copy.unlink()
            gone += 1
        except OSError:
            pass  # in use right now; it goes next time
    return gone


def clear_saves(conn: Any, folders: list[Path]) -> int:
    """Delete every save with its transcript, notes, collections, tags, plans
    and chats, and the files kept for them. Returns how many saves went.
    There is no way back: nothing is copied first."""
    gone = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table in SAVES_TABLES:
        if table in existing:
            conn.execute(f"DELETE FROM {table}")
    for folder in folders:
        _clear_folder(folder)
    return gone
