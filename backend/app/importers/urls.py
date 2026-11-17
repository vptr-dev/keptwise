"""Turning the many shapes of a post's link into one standard link.

The same video can appear as different links, e.g. TikTok's
"tiktokv.com/share/video/123/" and "tiktok.com/@chef/video/123?is_from_webapp=1".
Storing one standard ("canonical") link per video is what makes imports
duplicate-safe. Each function returns (standard link, video id or None),
or None when the link isn't from that platform.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

Canonical = tuple[str, str | None]

_TIKTOK_ID = re.compile(r"/(?:video|v|embed(?:/v2)?)/(\d{6,})")
_TIKTOK_AUTHOR = re.compile(r"/@([\w.\-]+)")
_INSTAGRAM_CODE = re.compile(r"^/(?:[\w.]+/)?(?:p|reel|reels|tv)/([\w-]+)")
_YOUTUBE_ID = re.compile(r"^[\w-]{11}$")
_FACEBOOK_REEL = re.compile(r"/reel/(\d+)")
_FACEBOOK_VIDEO = re.compile(r"/videos/(?:[\w.\-]+/)?(\d+)")
# Tracking bits added to links, which say nothing about the post itself.
_TRACKING = re.compile(r"^(utm_\w+|fbclid|igsh|igshid|mibextid|si|feature|ref|__tn__|__cft__\[0\])$")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _is_host(host: str, *domains: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def tiktok_author(url: str) -> str | None:
    """'@pasta.chef' in tiktok.com/@pasta.chef/video/123 -> 'pasta.chef'."""
    match = _TIKTOK_AUTHOR.search(urlsplit(url).path)
    return match.group(1) if match else None


def canonical_tiktok(url: str) -> Canonical | None:
    if not _is_host(_host(url), "tiktok.com", "tiktokv.com"):
        return None
    match = _TIKTOK_ID.search(urlsplit(url).path)
    if not match:
        return None
    video_id = match.group(1)
    # The share link works for everyone and yt-dlp understands it.
    return f"https://www.tiktokv.com/share/video/{video_id}/", video_id


def canonical_instagram(url: str) -> Canonical | None:
    if not _is_host(_host(url), "instagram.com", "instagr.am"):
        return None
    match = _INSTAGRAM_CODE.match(urlsplit(url).path)
    if not match:
        return None
    code = match.group(1)
    # Posts and reels share one set of codes, and /p/ opens both.
    return f"https://www.instagram.com/p/{code}/", code


def canonical_youtube(url_or_id: str) -> Canonical | None:
    text = url_or_id.strip()
    if _YOUTUBE_ID.match(text):
        video_id: str | None = text
    else:
        host = _host(text)
        parts = urlsplit(text)
        video_id = None
        if _is_host(host, "youtu.be"):
            video_id = parts.path.strip("/").split("/")[0]
        elif _is_host(host, "youtube.com"):
            if parts.path == "/watch":
                video_id = (parse_qs(parts.query).get("v") or [None])[0]
            else:
                match = re.match(r"^/(?:shorts|embed|live|v)/([\w-]{11})", parts.path)
                video_id = match.group(1) if match else None
        if not video_id or not _YOUTUBE_ID.match(video_id):
            return None
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def unwrap_redirect(url: str) -> str:
    """Facebook wraps outside links as l.facebook.com/l.php?u=<real link>."""
    parts = urlsplit(url)
    if _is_host((parts.hostname or "").lower(), "l.facebook.com", "lm.facebook.com", "l.instagram.com"):
        target = parse_qs(parts.query).get("u")
        if target:
            return unquote(target[0])
    return url


def clean_link(url: str) -> str:
    """Remove tracking bits (utm_..., fbclid, ...) and the #part from a link."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, values in parse_qs(parts.query, keep_blank_values=True).items()
        for value in values
        if not _TRACKING.match(key)
    ]
    host = (parts.hostname or "").lower()
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower() or "https", netloc, parts.path, urlencode(query), ""))


def canonical_facebook(url: str) -> Canonical:
    """Facebook saves can be videos, reels, posts or outside web pages.

    Videos and reels get one standard link each; anything else keeps its
    link with tracking removed.
    """
    url = unwrap_redirect(url)
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if _is_host(host, "facebook.com", "fb.com"):
        match = _FACEBOOK_REEL.search(parts.path)
        if match:
            return f"https://www.facebook.com/reel/{match.group(1)}", match.group(1)
        video_id = (parse_qs(parts.query).get("v") or [None])[0]
        if video_id and video_id.isdigit():
            return f"https://www.facebook.com/watch/?v={video_id}", video_id
        match = _FACEBOOK_VIDEO.search(parts.path)
        if match:
            # facebook.com/Tasty/videos/123 is the same video as watch/?v=123.
            return f"https://www.facebook.com/watch/?v={match.group(1)}", match.group(1)
        cleaned = clean_link(url.replace("://m.facebook.com", "://www.facebook.com"))
        return cleaned.replace("://facebook.com", "://www.facebook.com"), None
    return clean_link(url), None
