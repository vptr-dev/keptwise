"""An optional TikTok session held only in memory for this app run."""

from __future__ import annotations

import re
from copy import copy
from http.cookiejar import Cookie
from threading import Lock

MAX_SESSION_BYTES = 64 * 1024
_SESSION_NAMES = {"sessionid", "sessionid_ss", "sid_tt"}
_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"


def tiktok_host(host: str) -> bool:
    return re.fullmatch(rf"(?:{_LABEL}\.)*tiktok\.com", host.lower().lstrip(".")) is not None


class TikTokSession:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cookies: tuple[Cookie, ...] = ()

    def cookies(self) -> tuple[Cookie, ...]:
        with self._lock:
            live = tuple(cookie for cookie in self._cookies if not cookie.is_expired())
            if not any(cookie.name in _SESSION_NAMES for cookie in live):
                self._cookies = ()
                return ()
            return tuple(copy(cookie) for cookie in live)

    def clear(self) -> None:
        with self._lock:
            self._cookies = ()

    def load(self, content: str) -> None:
        # Netscape format is tab-separated. Never include a row in an error.
        rows = content.lstrip("\ufeff").splitlines()
        if not rows or rows[0].strip() not in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
            raise ValueError("Choose a TikTok cookies.txt file in Netscape format.")
        cookies = {}
        for row in rows[1:]:
            http_only = row.startswith("#HttpOnly_")
            if http_only:
                row = row.removeprefix("#HttpOnly_")
            if not row.strip() or row.startswith("#"):
                continue
            fields = row.split("\t")
            if len(fields) != 7:
                continue
            domain, scoped, path, _, expires, name, value = fields
            domain = domain.lower()
            if not tiktok_host(domain) or scoped not in ("TRUE", "FALSE"):
                continue
            if domain.startswith(".") != (scoped == "TRUE") or not path.startswith("/"):
                continue
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or not re.fullmatch(r"[^\x00-\x20;,\x7f]+", value):
                continue
            if not re.fullmatch(r"[0-9]{0,12}", expires):
                continue
            expiry = int(expires or 0) or None
            cookie = Cookie(
                version=0, name=name, value=value, port=None, port_specified=False,
                domain=domain, domain_specified=scoped == "TRUE", domain_initial_dot=domain.startswith("."),
                path=path, path_specified=True, secure=True, expires=expiry, discard=expiry is None,
                comment=None, comment_url=None, rest={"HttpOnly": None} if http_only else {},
            )
            if not cookie.is_expired():
                cookies[domain, path, name] = cookie
        if not any(cookie.name in _SESSION_NAMES for cookie in cookies.values()):
            raise ValueError("No active TikTok sign-in was found in this file. Sign in to TikTok and try again.")
        with self._lock:
            self._cookies = tuple(cookies.values())
