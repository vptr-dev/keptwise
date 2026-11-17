"""Reading the files inside an export, whether it's a zip or a folder.

Exports arrive as a zip file, an unpacked folder, or a folder that holds
the zip. ExportSource hides the difference: every file gets a name like
"your_instagram_activity/saved/saved_posts.json" and can be read the same
way. Files are read straight out of zips; nothing is unpacked to disk.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any


class ExportSource:
    def __init__(self) -> None:
        self._readers: dict[str, Callable[[], bytes]] = {}
        self._zips: list[zipfile.ZipFile] = []

    @classmethod
    def open(cls, path: Path) -> "ExportSource":
        source = cls()
        if path.is_dir():
            for file in sorted(path.rglob("*")):
                if not file.is_file():
                    continue
                name = file.relative_to(path).as_posix()
                if file.suffix.lower() == ".zip":
                    source._add_zip(file, prefix=name + "/")
                else:
                    source._readers[name] = file.read_bytes
        elif path.suffix.lower() == ".zip":
            source._add_zip(path, prefix="")
        elif path.is_file():
            source._readers[path.name] = path.read_bytes
        return source

    def _add_zip(self, file: Path, prefix: str) -> None:
        try:
            archive = zipfile.ZipFile(file)
        except zipfile.BadZipFile:
            return  # not really a zip; the import will say nothing was found
        self._zips.append(archive)
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = prefix + info.filename.replace("\\", "/")
            self._readers[name] = lambda archive=archive, info=info: archive.read(info)

    # ---------- reading ----------

    def names(self) -> list[str]:
        return list(self._readers)

    def named(self, filename: str) -> list[str]:
        """Every file with this exact file name (any folder, any case)."""
        wanted = filename.lower()
        return [name for name in self._readers if name.rsplit("/", 1)[-1].lower() == wanted]

    def read_text(self, name: str) -> str:
        # utf-8-sig also removes the invisible mark some programs put first.
        return self._readers[name]().decode("utf-8-sig", errors="replace")

    def read_json(self, name: str) -> Any:
        try:
            return json.loads(self.read_text(name))
        except json.JSONDecodeError:
            return None

    # ---------- closing ----------

    def close(self) -> None:
        for archive in self._zips:
            archive.close()
        self._zips.clear()

    def __enter__(self) -> "ExportSource":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
