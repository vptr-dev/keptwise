"""Download one big file with progress, Cancel and resume.

A download that stops half-way leaves "<name>.part" behind; next time it
asks the server for the rest only (an HTTP "Range" request).
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

CHUNK = 1024 * 1024


class Response(Protocol):
    status: int
    headers: Any

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


# (url, headers) -> an open response. Tests pass a fake one.
Opener = Callable[[str, dict[str, str]], Response]


class DownloadError(Exception):
    pass


def urllib_opener(url: str, headers: dict[str, str]) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": "Keptwise", **headers})
    try:
        return urllib.request.urlopen(request, timeout=60)  # type: ignore[no-any-return]
    except urllib.error.HTTPError as error:
        if error.code == 416:  # we already have the whole file
            return error  # type: ignore[return-value]
        raise DownloadError(f"The download server answered with error {error.code}.") from error
    except (urllib.error.URLError, OSError) as error:
        raise DownloadError(
            "Couldn't reach the download server. Check your internet connection and try again."
        ) from error


def download_file(
    url: str,
    dest: Path,
    expected_size: int | None = None,
    on_bytes: Callable[[int], None] | None = None,
    check: Callable[[], None] | None = None,
    opener: Opener = urllib_opener,
) -> Path:
    """Download url to dest. on_bytes(n) is called as bytes arrive (including resumed ones)."""
    if dest.is_file() and (expected_size is None or dest.stat().st_size == expected_size):
        if on_bytes:
            on_bytes(dest.stat().st_size)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if expected_size is not None and have > expected_size:
        part.unlink()
        have = 0

    headers = {"Range": f"bytes={have}-"} if have else {}
    response = opener(url, headers)
    try:
        if response.status == 416:
            pass  # the .part file already holds everything
        elif response.status == 206:
            pass  # the server sends the rest; keep what we have
        else:
            have = 0  # the server ignored Range; start again
        if on_bytes and have:
            on_bytes(have)
        if response.status != 416:
            with part.open("ab" if have else "wb") as file:
                while True:
                    if check:
                        check()
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    file.write(chunk)
                    if on_bytes:
                        on_bytes(len(chunk))
    except (OSError, http.client.HTTPException) as error:
        raise DownloadError(
            "The download was cut off. Try again and it will carry on where it stopped."
        ) from error
    finally:
        response.close()

    size = part.stat().st_size if part.exists() else 0
    if expected_size is not None and size != expected_size:
        raise DownloadError("The download stopped early. Try again and it will carry on where it stopped.")
    part.replace(dest)
    return dest
