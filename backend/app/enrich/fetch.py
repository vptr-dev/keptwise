"""Read video details and download media for local transcription using yt-dlp."""

from __future__ import annotations

import io
import re
import shutil
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.enrich.errors import plain_reason
from app.enrich.tiktok_session import TikTokSession, tiktok_host
from app.importers.urls import canonical_tiktok

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
    signed_in: bool = False


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

    def details(self, url: str, platform: str, author: str | None = None) -> tuple[VideoDetails, Any]:
        """Read the video page. The second value is passed to download_media."""
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
        # Try the video's own soundtrack even when the extractor can't label its codec.
        # Keep details even if TikTok only offers the separate music asset.
        return {"format": "best[acodec!=none][vcodec!=none]/best*[format_id!=audio][vcodec!=?none]/bestaudio",
                "format_sort": ["+size", "+br"]}
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


def tiktok_video_urls(url: str, author: str | None) -> tuple[str, ...]:
    canonical = canonical_tiktok(url)
    if not canonical:
        return (url,)
    _, video_id = canonical
    handle = (author or "").lstrip("@")
    fallback = f"https://www.tiktok.com/@_/video/{video_id}"
    if not re.fullmatch(r"[A-Za-z0-9_.]+", handle):
        original = re.fullmatch(r"/@([A-Za-z0-9_.]+)/video/\d+/?", urlsplit(url).path)
        handle = original[1] if original else "_"
    direct = f"https://www.tiktok.com/@{handle}/video/{video_id}"
    return tuple(dict.fromkeys((direct, fallback)))


def _scope_tiktok_jar(jar: Any) -> None:
    # The extractor can copy TikTok cookies to hosts listed in media URLs.
    # Apply this check at insertion so all yt-dlp HTTP backends see the same jar.
    set_cookie = jar.set_cookie

    def set_tiktok_cookie(cookie: Any) -> None:
        if tiktok_host(cookie.domain):
            cookie.secure = True
            set_cookie(cookie)

    jar.set_cookie = set_tiktok_cookie


class YtDlpFetcher:
    def __init__(self, ffmpeg_location: str | None = None, session: TikTokSession | None = None) -> None:
        self._session = session
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

        params = dict(options)
        use_session = params.pop("keptwise_tiktok", False)
        parts = urlsplit(url)
        session_cookies = (
            self._session.cookies()
            if use_session and self._session and parts.scheme == "https" and tiktok_host(parts.hostname or "")
            else ()
        )
        with yt_dlp.YoutubeDL(params) as ydl:
            if session_cookies:
                _scope_tiktok_jar(ydl.cookiejar)
                for cookie in session_cookies:
                    ydl.cookiejar.set_cookie(cookie)
            info = ydl.extract_info(url, download=False)
            cookies = list(ydl.cookiejar)
        if not isinstance(info, dict):
            raise RuntimeError("No media found")
        return _Page(url, options, info, cookies, signed_in=bool(session_cookies))

    def details(self, url: str, platform: str, author: str | None = None) -> tuple[VideoDetails, Any]:
        urls = tiktok_video_urls(url, author) if platform == "tiktok" else (url,)
        options = self._options(keptwise_tiktok=platform == "tiktok", **_format_for(platform))
        try:
            page = self._read(urls[0], options)
        except Exception as error:
            reason = plain_reason(error)
            if len(urls) == 1 or reason.kind not in {"private", "login", "blocked", "gone", "no_media", "unavailable"}:
                raise
            page = self._read(urls[1], options)
        return details_from_info(page.info), page

    def download_media(self, handle: Any, folder: Path, stem: str) -> Path:
        page: _Page = handle
        if page.options.get("keptwise_tiktok") and page.info.get("format_id") == "audio":
            raise OnlyMusic()
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
        options.pop("keptwise_tiktok", None)
        with yt_dlp.YoutubeDL(options) as ydl:
            if page.signed_in:
                _scope_tiktok_jar(ydl.cookiejar)
            # A prefetched page can reach the downloader after a disconnect.
            cookies = page.cookies if not page.signed_in or (self._session and self._session.cookies()) else []
            for cookie in cookies:
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


class OnlyMusic(Exception):
    """TikTok only provided the post's separate music asset."""


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
