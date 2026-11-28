"""Identify individual videos and resolve official share links."""

from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.db.items_repo import NewItem
from app.importers.urls import (
    Canonical,
    canonical_facebook,
    canonical_instagram,
    canonical_tiktok,
    canonical_youtube,
    tiktok_author,
)

HOSTS = {
    "tiktok": {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "tiktokv.com", "www.tiktokv.com"},
    "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"},
    "instagram": {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"},
    "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com", "mbasic.facebook.com", "web.facebook.com", "fb.com", "www.fb.com", "fb.watch"},
}
PLATFORM_FOR_HOST = {host: platform for platform, hosts in HOSTS.items() for host in hosts}
CANONICAL = {
    "tiktok": canonical_tiktok,
    "youtube": canonical_youtube,
    "instagram": canonical_instagram,
}
UNSUPPORTED = "Paste a link to an individual TikTok, YouTube video, Instagram post or reel, or Facebook video or post."
UNRESOLVED = "Couldn't open this share link. Open it in your browser and copy the full video or post link."


def _platform_url(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    platform = PLATFORM_FOR_HOST.get(host)
    if not platform or parts.scheme not in ("https", "http") or parts.username is not None or parts.port is not None:
        raise ValueError(UNSUPPORTED)
    return platform, parts._replace(scheme="https", netloc=host, fragment="").geturl()


def _short_link(platform: str, url: str) -> bool:
    parts = urlsplit(url)
    if platform == "tiktok":
        return parts.hostname in {"vm.tiktok.com", "vt.tiktok.com"} or parts.path.startswith("/t/")
    if platform == "facebook":
        return parts.hostname == "fb.watch" or parts.path.startswith("/share/")
    return platform == "instagram" and parts.path.startswith("/share/")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _redirect(url: str) -> str | None:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=5):
            return None
    except HTTPError as error:
        with error:
            if error.code in (301, 302, 303, 307, 308):
                return error.headers.get("Location")
        return None


def _canonical(platform: str, url: str) -> Canonical | None:
    parts = urlsplit(url)
    if platform == "youtube" and parts.hostname in {"youtube-nocookie.com", "www.youtube-nocookie.com"}:
        url = parts._replace(netloc="www.youtube.com").geturl()
    if platform == "facebook":
        url = parts._replace(netloc="www.facebook.com").geturl()
        canonical = canonical_facebook(url)
        if canonical[1] is not None or re.search(r"/(?:posts|permalink)/[^/]+", parts.path):
            return canonical
        if parts.path in {"/story.php", "/permalink.php"} and re.search(r"(?:^|&)story_fbid=[^&]+", parts.query):
            return canonical
        return None
    return CANONICAL[platform](url)


def pasted_item(value: str) -> NewItem:
    url = value.strip()
    if not url or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError(UNSUPPORTED)
    if "://" not in url:
        url = "https://" + url
    platform, url = _platform_url(url)
    for redirects in range(5):
        if not _short_link(platform, url):
            canonical = _canonical(platform, url)
            if canonical:
                normalized, external_id = canonical
                author = tiktok_author(url) if platform == "tiktok" else None
                return NewItem(platform, normalized, author=author, external_id=external_id)
            raise ValueError(UNRESOLVED if redirects else UNSUPPORTED)
        if redirects == 4:
            break
        try:
            location = _redirect(url)
            if not location:
                break
            destination, url = _platform_url(urljoin(url, location))
            if destination != platform:
                break
        except (URLError, OSError, ValueError):
            break
    raise ValueError(UNRESOLVED)
