"""Importers for TikTok, YouTube, Instagram and Facebook data exports.

parse_export() runs every platform's reader over the files, so one drop can
hold several exports at once (e.g. a folder with the TikTok and Instagram
zips in it).
"""

from __future__ import annotations

from collections.abc import Callable

from app.importers import facebook, instagram, tiktok, youtube
from app.importers.common import ParseResult
from app.importers.source import ExportSource

Parser = Callable[[ExportSource], ParseResult | None]

PARSERS: list[Parser] = [tiktok.parse, youtube.parse, instagram.parse, facebook.parse]

PLATFORM_NAMES = {
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "instagram": "Instagram",
    "facebook": "Facebook",
}

# When a whole unzipped export folder is dropped, the window only copies
# the files the readers above use (plus any zips and CSVs), never photos,
# videos or messages. Keep this in step with the readers.
WANTED_FILE_NAMES = sorted(
    {
        *tiktok.JSON_NAMES,
        "favorite videos.txt",
        "like list.txt",
        "saved_posts.json",
        "saved_collections.json",
        "saved_posts.html",
        "saved_collections.html",
        *facebook.FILE_NAMES,
        "saved_items_and_collections.html",
    }
)
WANTED_EXTENSIONS = [".zip", ".csv"]


def parse_export(source: ExportSource) -> list[ParseResult]:
    """Results for every platform found in the files (empty list: none found)."""
    results = []
    for parser in PARSERS:
        result = parser(source)
        if result is not None:
            results.append(result)
    return results
