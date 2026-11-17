"""TikTok: "Download your data" export, JSON or TXT format.

Where the saves are (checked against the user's real export, Nov 2026):
- JSON: user_data_tiktok.json (older exports: user_data.json) holds
  "Likes and Favorites" (older exports: "Activity") -> "Favorite Videos" ->
  "FavoriteVideoList": [{"Date": "2026-11-10 19:43:17",
  "Link": "https://www.tiktokv.com/share/video/<id>/"}]. Dates are UTC.
- TXT: a file "Favorite Videos.txt" with "Date: ..." and "Link: ..." lines.

Collections: "Favorite Collection" -> "FavoriteCollectionList":
[{"Date": ..., "FavoriteCollection": "Gym"}] lists the names only. TikTok
doesn't say which videos are in which collection, so videos come in without
one and the names are only shown in the import summary.

"Like List" -> "ItemFavoriteList" (likes) and favourite sounds, effects
and hashtags are not saves, so they are counted in a note but not imported.
Empty lists may be null instead of [].
"""

from __future__ import annotations

import re

from app.importers.common import (
    Collector,
    ParseResult,
    find_key,
    get_ci,
    iso_from_text,
    plural,
)
from app.importers.source import ExportSource
from app.importers.urls import canonical_tiktok, tiktok_author

PLATFORM = "tiktok"
JSON_NAMES = ("user_data_tiktok.json", "user_data.json")
_TXT_LINK = re.compile(r"^\s*Link:\s*(\S+)", re.IGNORECASE)
_TXT_DATE = re.compile(r"^\s*Date:\s*(.+?)\s*$", re.IGNORECASE)


def parse(source: ExportSource) -> ParseResult | None:
    json_files = [name for wanted in JSON_NAMES for name in source.named(wanted)]
    txt_files = source.named("Favorite Videos.txt")
    if not json_files and not txt_files:
        return None

    found = Collector(PLATFORM)
    collection_names: list[str] = []
    likes = 0
    other_favourites = 0
    bad_links = 0

    for name in json_files:
        data = source.read_json(name)
        for entries in find_key(data, "FavoriteVideoList"):
            for entry in entries if isinstance(entries, list) else []:
                link = get_ci(entry, "Link", "VideoLink") if isinstance(entry, dict) else None
                if not _add(found, link, get_ci(entry, "Date") if link else None):
                    bad_links += 1
        for entries in find_key(data, "FavoriteCollectionList"):
            for entry in entries if isinstance(entries, list) else []:
                name = get_ci(entry, "FavoriteCollection", "Name") if isinstance(entry, dict) else None
                if isinstance(name, str) and name.strip() and name.strip() not in collection_names:
                    collection_names.append(name.strip())
        for entries in find_key(data, "ItemFavoriteList"):  # the "Like List"
            likes += len(entries) if isinstance(entries, list) else 0
        for key in ("FavoriteSoundList", "FavoriteEffectsList", "FavoriteHashtagList"):
            for entries in find_key(data, key):
                other_favourites += len(entries) if isinstance(entries, list) else 0

    for name in txt_files:
        date: str | None = None
        for line in source.read_text(name).splitlines():
            if match := _TXT_DATE.match(line):
                date = match.group(1)
            elif match := _TXT_LINK.match(line):
                if not _add(found, match.group(1), date):
                    bad_links += 1
                date = None
    for name in source.named("Like List.txt"):
        likes += sum(1 for line in source.read_text(name).splitlines() if _TXT_LINK.match(line))

    if not found:
        found.notes.append("This TikTok export has no favourite videos.")
    if likes:
        found.notes.append(f"Skipped {plural(likes, 'liked video')}: likes aren't saves.")
    if other_favourites:
        found.notes.append(
            f"Skipped {plural(other_favourites, 'favourite sound, effect or hashtag', 'favourite sounds, effects and hashtags')}."
        )
    if bad_links:
        found.notes.append(f"Skipped {plural(bad_links, 'entry', 'entries')} without a video link.")
    if collection_names:
        found.notes.append(
            f"TikTok lists your {plural(len(collection_names), 'collection')} but not which videos are in "
            "each, so the videos come in without a collection."
        )
    result = found.result()
    result.collections = collection_names
    return result


def _add(found: Collector, link: object, date: object) -> bool:
    """Add one favourite. False if the link isn't a TikTok video."""
    if not isinstance(link, str):
        return False
    canonical = canonical_tiktok(link.strip())
    if canonical is None:
        return False
    url, video_id = canonical
    found.add(
        url,
        external_id=video_id,
        author=tiktok_author(link),
        saved_at=iso_from_text(date if isinstance(date, str) else None),
    )
    return True
