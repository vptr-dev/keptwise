"""A fake network for tests: answers HTTP calls from a table of responses."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

from app.ai.http import HttpClient, HttpError, HttpResponse

Reply = Any | Callable[[dict[str, Any] | None], Any]


class FakeNet:
    """Register replies by (method, url prefix); records every request made."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, str, Reply]] = []
        self.requests: list[dict[str, Any]] = []

    def on(self, method: str, url_prefix: str, reply: Reply) -> "FakeNet":
        """reply: a JSON value, an HttpError to raise, or fn(request_json) -> value."""
        self.routes.insert(0, (method, url_prefix, reply))  # newest wins
        return self

    def _answer(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> Any:
        payload = json.loads(body) if body else None
        self.requests.append({"method": method, "url": url, "headers": headers, "json": payload})
        for route_method, prefix, reply in self.routes:
            if route_method == method and url.startswith(prefix):
                if isinstance(reply, HttpError):
                    raise reply
                return reply(payload) if callable(reply) else reply
        raise HttpError("Couldn't connect: no fake route", status=None)

    def transport(self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> HttpResponse:
        return HttpResponse(200, json.dumps(self._answer(method, url, headers, body)).encode())

    def line_transport(self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Iterator[bytes]:
        for line in self._answer(method, url, headers, body):
            yield json.dumps(line).encode()

    def client(self) -> HttpClient:
        return HttpClient(self.transport, self.line_transport)
