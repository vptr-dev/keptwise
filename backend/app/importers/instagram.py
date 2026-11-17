"""Instagram: Meta "Download your information" export.

Where the saves are (JSON format):
- your_instagram_activity/saved/saved_posts.json (older: saved/saved_posts.json)
  "saved_saved_media": [{"title": <who posted it>,
      "string_map_data": {"Saved on": {"href": <link>, "timestamp": <unix>}}}]
- .../saved/saved_collections.json
  "saved_saved_collections": a list where a collection's name comes first
  ({"title": "Collection", "string_map_data": {"Name": {"value": <name>}}})
  followed by the posts in it ({"string_map_data": {"Name": {"href": <link>,
  "value": <who posted it>}, "Added Time": {"timestamp": <unix>}}}).

If the export was made in HTML format, only the links can be read.
Meta writes letters like "é" garbled; fix_meta_text repairs them.
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
from app.importers.urls import canonical_instagram

PLATFORM = "instagram"
_HTML_LINK = re.compile(r"""href=["'](https?://(?:www\.)?instagram\.com/[^"']+)["']""", re.IGNORECASE)
HTML_NOTE = (
    "This Instagram export is in HTML format, so only the links could be read "
    "(no dates or collections). For full details, request it again in JSON format."
)


def parse(source: ExportSource) -> ParseResult | None:
    posts = source.named("saved_posts.json")
    collections = source.named("saved_collections.json")
    html = source.named("saved_posts.html") + source.named("saved_collections.html")
    if not posts and not collections and not html:
        return None

    found = Collector(PLATFORM)
    skipped = 0
    for name in posts:
        for entry in _entries(source.read_json(name)):
            if not _add_post(found, entry, collection=None):
                skipped += 1
    for name in collections:
        current: str | None = None
        for entry in _entries(source.read_json(name)):
            link = _instagram_link(entry)
            if link is None:
                # An entry without a post link starts a new collection.
                current = _collection_name(entry) or current
            else:
                _add_post(found, entry, collection=current)
    if not posts and not collections:
        for name in html:
            for link in _HTML_LINK.findall(source.read_text(name)):
                canonical = canonical_instagram(link)
                if canonical:
                    found.add(canonical[0], external_id=canonical[1])
        found.notes.append(HTML_NOTE)

    if not found:
        found.notes.append("This Instagram export has no saved posts.")
    if skipped:
        found.notes.append(f"Skipped {plural(skipped, 'entry', 'entries')} without a post link.")
    return found.result()


def _entries(data: Any) -> list[dict[str, Any]]:
    """The list of entries in a saved_*.json file, whatever its top key is."""
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return [entry for entry in value if isinstance(entry, dict)]
    return []


def _instagram_link(entry: dict[str, Any]) -> tuple[str, str] | None:
    for href in find_key(entry, "href"):
        if isinstance(href, str) and (canonical := canonical_instagram(href)):
            return canonical
    return None


def _collection_name(entry: dict[str, Any]) -> str | None:
    for name_field in find_key(entry, "Name"):
        if isinstance(name_field, dict) and isinstance(name_field.get("value"), str):
            return fix_meta_text(name_field["value"])
    title = entry.get("title")
    if isinstance(title, str) and title.lower() != "collection":
        return fix_meta_text(title)
    return None


def _add_post(found: Collector, entry: dict[str, Any], collection: str | None) -> bool:
    canonical = _instagram_link(entry)
    if canonical is None:
        return False
    author = entry.get("title")
    if not isinstance(author, str) or not author:
        # In collections the poster's name sits next to the link.
        author = next(
            (
                field["value"]
                for field in find_key(entry, "Name")
                if isinstance(field, dict) and isinstance(field.get("value"), str)
            ),
            None,
        )
    timestamp = next(iter(find_key(entry, "timestamp")), None)
    found.add(
        canonical[0],
        external_id=canonical[1],
        author=fix_meta_text(author),
        saved_at=iso_from_timestamp(timestamp),
        collection=collection,
    )
    return True
