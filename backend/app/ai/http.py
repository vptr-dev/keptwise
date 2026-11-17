"""A tiny HTTP client for talking to AI providers.

It uses only Python's built-in urllib. Tests swap the "transport" for a
fake one, so no real network calls happen in tests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class HttpError(Exception):
    """The server answered with an error, or couldn't be reached."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status  # None = couldn't connect at all
        self.body = body


@dataclass
class HttpResponse:
    status: int
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8") or "null")


# (method, url, headers, body, timeout) -> response
Transport = Callable[[str, str, dict[str, str], bytes | None, float], HttpResponse]
# Same, but yields the response one line at a time (for streamed answers).
LineTransport = Callable[[str, str, dict[str, str], bytes | None, float], Iterator[bytes]]


def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def _opener(url: str) -> urllib.request.OpenerDirector:
    if _is_local(url):
        # Programs on this PC must be reached directly, never via a proxy.
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def direct_local_url(url: str) -> str:
    """Use 127.0.0.1 instead of "localhost".

    Windows tries "localhost" over IPv6 first. Ollama and LM Studio listen on
    IPv4 only, so every call would wait about 2 seconds before falling back.
    """
    parts = urlparse(url)
    if parts.hostname != "localhost":
        return url
    return parts._replace(netloc=parts.netloc.replace("localhost", "127.0.0.1", 1)).geturl()


def _open(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float):  # type: ignore[no-untyped-def]
    url = direct_local_url(url)
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        return _opener(url).open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        raise HttpError(f"HTTP {error.code}", status=error.code, body=text) from error
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise HttpError(f"Couldn't connect: {reason}") from error


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> HttpResponse:
    with _open(method, url, headers, body, timeout) as response:
        return HttpResponse(response.status, response.read())


def urllib_line_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> Iterator[bytes]:
    with _open(method, url, headers, body, timeout) as response:
        for line in response:
            if line.strip():
                yield line


class HttpClient:
    def __init__(
        self,
        transport: Transport = urllib_transport,
        line_transport: LineTransport = urllib_line_transport,
    ) -> None:
        self._transport = transport
        self._line_transport = line_transport

    def get_json(self, url: str, headers: dict[str, str] | None = None, timeout: float = 15) -> Any:
        return self._transport("GET", url, dict(headers or {}), None, timeout).json()

    def post_json(
        self,
        url: str,
        payload: Any,
        headers: dict[str, str] | None = None,
        timeout: float = 120,
    ) -> Any:
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(payload).encode("utf-8")
        return self._transport("POST", url, all_headers, body, timeout).json()

    def delete_json(
        self,
        url: str,
        payload: Any,
        headers: dict[str, str] | None = None,
        timeout: float = 30,
    ) -> Any:
        """DELETE with a JSON body (Ollama's way of deleting a model)."""
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(payload).encode("utf-8")
        return self._transport("DELETE", url, all_headers, body, timeout).json()

    def post_json_lines(
        self,
        url: str,
        payload: Any,
        headers: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> Iterator[Any]:
        """POST, then yield each line of the answer as a JSON object."""
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(payload).encode("utf-8")
        for line in self._line_transport("POST", url, all_headers, body, timeout):
            yield json.loads(line.decode("utf-8"))
