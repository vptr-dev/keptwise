"""Get a video's public details and its sound, using yt-dlp.

The app only reads public pages: it never signs in and never sends
cookies, so private videos simply fail with a clear reason.

Checked on real TikTok saves (Nov 2026):
- The share links from TikTok's export work as they are.
- TikTok's "audio" format is the background song, not the video's own
  sound, so for TikTok we take the smallest file that has both picture and
  sound, and only use "audio" when there's nothing else (photo slideshows).
- Thumbnail links expire after a while, so a small copy is kept locally.
- About a third of TikTok page reads give file links that all answer 403;
  a fresh read usually works (DOWNLOAD_TRIES, with a short pause).
- TikTok refuses the page itself to OpenSSL 3.0's TLS 1.3 handshake (the
  python.org 3.12 builds). The app is built on a Python with OpenSSL 3.5
  (packaging/build.ps1 checks).
"""

from __future__ import annotations

import io
import shutil
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

# Longest video the app transcribes (longer ones get details only).
MAX_MINUTES = 90
# Biggest file the app downloads for its sound.
MAX_DOWNLOAD_BYTES = 400 * 1024 * 1024
THUMBNAIL_WIDTH = 480
# TikTok sometimes hands out file links that all answer 403 (about one
# read in three); reading the page again gives new links that usually work.
# 3 tries still left ~4% of videos without sound; 6 leaves about 1 in 700,
# and those stay waiting for the next run (app/enrich/job.py).
DOWNLOAD_TRIES = 6
RETRY_PAUSE_S = 1.5


@dataclass
class _Page:
    """A read page: what download_media needs to fetch the file."""

    url: str
    options: dict[str, Any]
    info: dict[str, Any]
    cookies: list[Any]


def forbidden(error: object) -> bool:
    """TikTok refused the file (HTTP 403). Worth trying again later."""
    return "HTTP Error 403" in str(error)




@dataclass
class VideoDetails:
    title: str | None = None
    description: str | None = None
    author: str | None = None
    duration_s: float | None = None
    thumbnail_url: str | None = None
    posted_at: str | None = None


class Fetcher(Protocol):
    """What the enrichment job needs. Tests use a fake one."""

    def details(self, url: str, platform: str) -> tuple[VideoDetails, Any]:
        """Read the public page. The second value is passed to download_media."""
        ...

    def download_media(self, handle: Any, folder: Path, stem: str) -> Path:
        """Download the file that holds the video's sound. Returns its path."""
        ...

    def download_thumbnail(self, url: str, path: Path) -> Path:
        ...


class _QuietLogger:
    """Keeps yt-dlp from printing to the console; errors still raise."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def _format_for(platform: str) -> dict[str, Any]:
    if platform == "tiktok":
        # Smallest file with the video's own sound; the song only as a last resort.
        return {"format": "best[acodec!=none][vcodec!=none]/bestaudio", "format_sort": ["+size", "+br"]}
    # YouTube, Instagram and Facebook have sound-only files of the video itself.
    return {"format": "bestaudio/best[acodec!=none]", "format_sort": ["+size", "+br"]}


def _iso_from_details(info: dict[str, Any]) -> str | None:
    timestamp = info.get("timestamp")
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    upload_date = info.get("upload_date")
    if isinstance(upload_date, str) and len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00Z"
    return None


def details_from_info(info: dict[str, Any]) -> VideoDetails:
    """Pick the fields the app keeps from yt-dlp's (very big) info dict."""
    description = (info.get("description") or "").strip() or None
    title = (info.get("title") or "").strip() or None
    # TikTok has no titles: yt-dlp uses the start of the caption instead.
    if title and description and description.startswith(title.rstrip("…. ")):
        title = None
    author = info.get("uploader") or info.get("channel") or info.get("uploader_id") or info.get("creator")
    duration = info.get("duration")
    return VideoDetails(
        title=title,
        description=description,
        author=str(author).strip() if author else None,
        duration_s=float(duration) if isinstance(duration, (int, float)) and duration > 0 else None,
        thumbnail_url=info.get("thumbnail") or None,
        posted_at=_iso_from_details(info),
    )


def bundled_ffmpeg(base: Path | None = None, frozen: bool | None = None) -> str | None:
    """ffmpeg.exe shipped inside the installed app, if the build included it.

    Downloads here are single files, and PyAV decodes the sound itself, so
    ffmpeg is only a fallback yt-dlp uses for a few streaming formats.
    """
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return None
    folder = base or Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    path = folder / "ffmpeg" / "ffmpeg.exe"
    return str(path) if path.is_file() else None


class YtDlpFetcher:
    def __init__(self, ffmpeg_location: str | None = None) -> None:
        self._ffmpeg = ffmpeg_location or bundled_ffmpeg() or shutil.which("ffmpeg")

    def _options(self, **extra: Any) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _QuietLogger(),
            "noplaylist": True,
            "cachedir": False,  # don't write yt-dlp's cache outside the data folder
            "socket_timeout": 30,
            "retries": 3,
            "max_filesize": MAX_DOWNLOAD_BYTES,
            "continuedl": True,  # a half-finished download carries on next time
        }
        if self._ffmpeg:
            options["ffmpeg_location"] = self._ffmpeg
        options.update(extra)
        return options

    def _read(self, url: str, options: dict[str, Any]) -> _Page:
        import yt_dlp  # imported here: it's big and only needed for this

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            cookies = list(ydl.cookiejar)  # carried over to the download, like one yt-dlp run
        if not isinstance(info, dict):
            raise RuntimeError("No media found")
        return _Page(url, options, info, cookies)

    def details(self, url: str, platform: str) -> tuple[VideoDetails, Any]:
        page = self._read(url, self._options(**_format_for(platform)))
        return details_from_info(page.info), page

    def download_media(self, handle: Any, folder: Path, stem: str) -> Path:
        page: _Page = handle
        duration = page.info.get("duration")
        if isinstance(duration, (int, float)) and duration > MAX_MINUTES * 60:
            raise TooLong(f"This video is longer than {MAX_MINUTES} minutes, so it isn't transcribed.")
        folder.mkdir(parents=True, exist_ok=True)
        for attempt in range(DOWNLOAD_TRIES):
            try:
                return self._download(page, folder, stem)
            except Exception as error:
                if not forbidden(error) or attempt == DOWNLOAD_TRIES - 1:
                    raise
                time.sleep(RETRY_PAUSE_S)
                page = self._read(page.url, page.options)  # fresh links
        raise AssertionError("unreachable")

    def _download(self, page: _Page, folder: Path, stem: str) -> Path:
        import yt_dlp

        options = dict(page.options, outtmpl=str(folder / f"{stem}.%(ext)s"))
        with yt_dlp.YoutubeDL(options) as ydl:
            for cookie in page.cookies:
                ydl.cookiejar.set_cookie(cookie)
            done = ydl.process_ie_result(dict(page.info), download=True)
        downloads = (done or {}).get("requested_downloads") or []
        for download in downloads:
            path = Path(download.get("filepath") or "")
            if path.is_file():
                return path
        found = sorted(p for p in folder.glob(f"{stem}.*") if not p.name.endswith(".part"))
        if found:
            return found[0]
        raise RuntimeError("no media file was downloaded")

    def download_thumbnail(self, url: str, path: Path) -> Path:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(10 * 1024 * 1024)
        return save_thumbnail(data, path)


class TooLong(Exception):
    """The video is too long to transcribe (details are still kept)."""


def save_thumbnail(data: bytes, path: Path) -> Path:
    """Save a small JPEG copy. Falls back to the original bytes if it can't be read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            if image.width > THUMBNAIL_WIDTH:
                height = round(image.height * THUMBNAIL_WIDTH / image.width)
                image = image.resize((THUMBNAIL_WIDTH, height))
            image.save(path, "JPEG", quality=82)
    except Exception:  # noqa: BLE001 - an odd image format must not fail the item
        path.write_bytes(data)
    return path
