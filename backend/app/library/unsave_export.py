"""The "Safe to unsave" list as a CSV file the user can open in Excel.

The file goes to the user's Downloads folder (the app window can't
download files itself). Nothing is sent anywhere.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path
from typing import Any

COLUMNS = ["Platform", "Link", "Title", "Creator", "Saved on", "Collections", "Unsaved yet"]


def _cell(value: Any) -> str:
    """Text for one cell. A leading = + - @ would make Excel run it as a formula, so it is quoted."""
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def to_csv(cards: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for card in cards:
        writer.writerow([
            _cell(card.get("platform_name")),
            _cell(card.get("url")),
            _cell(card.get("title")),
            _cell(card.get("author")),
            _cell((card.get("saved_at") or "")[:10]),
            _cell(", ".join(link["name"] for link in card.get("collections", []))),
            "yes" if card.get("unsaved") else "no",
        ])
    return out.getvalue()


def downloads_folder() -> Path:
    """The user's Downloads folder, or their home folder if there isn't one."""
    folder = Path.home() / "Downloads"
    return folder if folder.is_dir() else Path.home()


def save_csv(text: str, folder: Path, today: date | None = None) -> Path:
    """Write the CSV next to any earlier ones without overwriting them."""
    stem = f"saves-to-unsave-{(today or date.today()).isoformat()}"
    path = folder / f"{stem}.csv"
    number = 2
    while path.exists():
        path = folder / f"{stem} ({number}).csv"
        number += 1
    # utf-8-sig: Excel then shows emoji and accents correctly.
    path.write_text(text, encoding="utf-8-sig", newline="")
    return path
