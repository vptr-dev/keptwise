"""Facebook: Meta "Download your information" export.

Where the saves are (JSON format):
- your_activity_across_facebook/saved_items_and_collections/
  saved_items_and_collections.json (older exports: saved_items_and_collections/...)
  "saves_and_collections_v2": [{"timestamp": <unix>, "title": "... saved a video.",
      "attachments": [{"data": [{"external_context":
          {"name": <post title>, "source": <who posted it>, "url": <link>}}]}]}]
  Entries whose title says "... added ... to <Collection>." put the item in
  that collection.
- Older exports may also have saved_items.json / collections.json with the
  same kind of entries.

Facebook saves can also be outside web pages (articles, shops). Those are
imported too, with tracking bits removed from the link.
"""

from __future__ import annotations

import re
from typing import Any

from app.importers.common import (
    Collector,
    ParseResult,
    find_key,
    fix_meta_text,
    iso_from_timestamp,
    plural,
)
from app.importers.source import ExportSource
from app.importers.urls import canonical_facebook

PLATFORM = "facebook"
FILE_NAMES = ("saved_items_and_collections.json", "saved_items.json", "collections.json")
# "Ana added a video from Tasty to Recipes." -> "Recipes"
_ADDED_TO = re.compile(r"\badded\b.*\bto (?:the |your )?(?P<name>.+?)(?: collection)?\.?\s*$", re.IGNORECASE)
_HTML_NOTE = (
    "This Facebook export is in HTML format, which can't be read reliably. "
    "Please request it again in JSON format."
)


def parse(source: ExportSource) -> ParseResult | None:
    files = [name for wanted in FILE_NAMES for name in source.named(wanted)]
    files = [name for name in files if "facebook" in name.lower() or "saved" in name.lower()]
    html = source.named("saved_items_and_collections.html")
    if not files and not html:
        return None

    found = Collector(PLATFORM)
    no_link = 0
    for name in files:
        for entry in _entries(source.read_json(name)):
            if not _add_entry(found, entry):
                no_link += 1
    if not files:
        found.notes.append(_HTML_NOTE)
    elif not found:
        found.notes.append("This Facebook export has no saved items with links.")
    if no_link:
        found.notes.append(
            f"Skipped {plural(no_link, 'saved item')} with no link (for example photos)."
        )
    return found.result()


def _entries(data: Any) -> list[dict[str, Any]]:
    """All entries in the file, from every top-level list."""
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    entries: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                entries.extend(entry for entry in value if isinstance(entry, dict))
    return entries


def _first_link(entry: dict[str, Any]) -> str | None:
    for key in ("url", "href"):
        for value in find_key(entry, key):
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None


def _first_text(entry: dict[str, Any], key: str) -> str | None:
    for value in find_key(entry, key):
        if isinstance(value, str) and value.strip():
            return fix_meta_text(value)
    return None


def _add_entry(found: Collector, entry: dict[str, Any]) -> bool:
    link = _first_link(entry)
    if link is None:
        return False
    url, video_id = canonical_facebook(link)
    title = fix_meta_text(entry.get("title")) or ""
    match = _ADDED_TO.search(title)
    found.add(
        url,
        external_id=video_id,
        author=_first_text(entry, "source"),
        caption=_first_text(entry, "name"),
        saved_at=iso_from_timestamp(entry.get("timestamp")),
        collection=match.group("name") if match else None,
    )
    return True
