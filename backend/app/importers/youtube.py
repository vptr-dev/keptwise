"""YouTube: Google Takeout export.

Where the saves are: Takeout/YouTube and YouTube Music/playlists/ holds one
CSV file per playlist (the folder name changes with your Google language).
- Newer exports: "<Playlist name>-videos.csv" with the columns
  "Video ID, Playlist Video Creation Timestamp". playlists.csv lists the
  playlists themselves and has no videos.
- Older exports: "<Playlist name>.csv" with the playlist's details first,
  a blank line, then "Video ID, Time Added" rows.

Each playlist (including "Watch later") becomes a platform collection.
"Liked videos" are likes, not saves, so they are counted but not imported.
"""

from __future__ import annotations

import csv
import io

from app.importers.common import Collector, ParseResult, iso_from_text, plural
from app.importers.source import ExportSource
from app.importers.urls import canonical_youtube

PLATFORM = "youtube"
LIKED = {"liked videos", "liked music"}


def parse(source: ExportSource) -> ParseResult | None:
    found = Collector(PLATFORM)
    saw_playlists = False
    liked = 0
    for name in source.names():
        if not name.lower().endswith(".csv"):
            continue
        rows = list(csv.reader(io.StringIO(source.read_text(name))))
        videos = _video_rows(rows)
        if videos is None:
            continue  # not a playlist file (e.g. playlists.csv, subscriptions.csv)
        saw_playlists = True
        playlist = _playlist_name(name, rows)
        if playlist.lower() in LIKED:
            liked += len(videos)
            continue
        for video_id, added in videos:
            canonical = canonical_youtube(video_id)
            if canonical:
                found.add(
                    canonical[0],
                    external_id=canonical[1],
                    saved_at=iso_from_text(added),
                    collection=playlist,
                )

    if not saw_playlists:
        return None
    if not found:
        found.notes.append("This YouTube export has no videos in your playlists.")
    if liked:
        found.notes.append(f"Skipped {plural(liked, 'liked video')}: likes aren't saves.")
    return found.result()


def _video_rows(rows: list[list[str]]) -> list[tuple[str, str | None]] | None:
    """(video id, date added) for each video, or None if there's no Video ID column."""
    for index, row in enumerate(rows):
        header = [cell.strip().lower() for cell in row]
        if "video id" not in header:
            continue
        id_column = header.index("video id")
        time_column = next(
            (n for n, cell in enumerate(header) if "timestamp" in cell or "time added" in cell),
            None,
        )
        videos: list[tuple[str, str | None]] = []
        for data in rows[index + 1 :]:
            if not any(cell.strip() for cell in data):
                break  # a blank line ends the list
            if len(data) > id_column and data[id_column].strip():
                added = data[time_column] if time_column is not None and len(data) > time_column else None
                videos.append((data[id_column].strip(), added))
        return videos
    return None


def _playlist_name(file_name: str, rows: list[list[str]]) -> str:
    # Older exports name the playlist in a "Title" column above the videos.
    if len(rows) >= 2:
        header = [cell.strip().lower() for cell in rows[0]]
        if "title" in header and "video id" not in header:
            title = rows[1][header.index("title")].strip() if len(rows[1]) > header.index("title") else ""
            if title:
                return title
    stem = file_name.rsplit("/", 1)[-1][: -len(".csv")]
    return stem[: -len("-videos")] if stem.lower().endswith("-videos") else stem
