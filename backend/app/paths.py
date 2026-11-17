"""Where the app keeps the user's data on this computer.

Everything lives in one folder, %APPDATA%\\Keptwise by default, so it
survives app updates and uninstalls. Tests and developers can point the app
somewhere else with the KEPTWISE_DATA_DIR environment variable.

Older versions used %APPDATA%\\SavesKnowledge. The first time this version
starts, that folder is renamed to Keptwise, so nothing is lost.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATA_DIR_ENV = "KEPTWISE_DATA_DIR"
APP_FOLDER_NAME = "Keptwise"
OLD_FOLDER_NAME = "SavesKnowledge"  # the folder's name in older versions


def has_saves(folder: Path) -> bool:
    """Does this data folder hold any imported saves?"""
    database = folder / "saves.db"
    if not database.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT EXISTS (SELECT 1 FROM items)").fetchone()[0] == 1
        finally:
            conn.close()
    except sqlite3.Error:
        return True  # can't tell: treat it as precious


def move_old_folder(old: Path, new: Path) -> Path:
    """Rename an older version's data folder to the new name.

    If a new folder already exists but holds no saves while the old one does
    (an empty one made by a test run, say), the empty one is renamed aside,
    never deleted, and the old one moves in.

    Returns the folder to use: the new one, or the old one if it couldn't be
    renamed (for example because an old copy of the app is still open)."""
    if not old.is_dir():
        return new
    if new.exists():
        if has_saves(new) or not has_saves(old):
            return new  # the new folder is the real one
        try:
            new.rename(new.with_name(f"{new.name}-empty-{datetime.now():%Y%m%d-%H%M%S}"))
        except OSError:
            return old
    try:
        old.rename(new)
        return new
    except OSError:
        return old


def default_data_dir() -> Path:
    """The data folder to use when nobody chose one."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        return move_old_folder(Path(appdata) / OLD_FOLDER_NAME, Path(appdata) / APP_FOLDER_NAME)
    return move_old_folder(Path.home() / ".saves-knowledge", Path.home() / ".keptwise")  # macOS / Linux


@dataclass(frozen=True)
class AppPaths:
    """All the folders and files inside the data folder."""

    root: Path

    @property
    def database(self) -> Path:
        return self.root / "saves.db"

    @property
    def thumbnails(self) -> Path:
        return self.root / "thumbnails"

    @property
    def collection_icons(self) -> Path:
        """Pictures the user put on collections."""
        return self.root / "collection-icons"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def models(self) -> Path:
        """Downloaded speech and search models."""
        return self.root / "models"

    @property
    def imports(self) -> Path:
        """Copies of export files the user dragged in."""
        return self.root / "imports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def create(self) -> "AppPaths":
        """Make sure every folder exists. Returns self for chaining."""
        for folder in (
            self.root,
            self.thumbnails,
            self.collection_icons,
            self.audio,
            self.models,
            self.imports,
            self.logs,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        return self
