"""A small message board that background jobs post updates to.

The UI listens on /api/events (Server-Sent Events) and receives every
update as it happens. Each message gets a growing number (seq), so a
listener can ask "what happened after message 41?".
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    seq: int
    type: str  # e.g. "job"
    data: dict[str, Any]


class EventHub:
    def __init__(self, keep: int = 500) -> None:
        self._events: deque[Event] = deque(maxlen=keep)
        self._seq = 0
        self._closed = False
        self._cond = threading.Condition()

    @property
    def last_seq(self) -> int:
        with self._cond:
            return self._seq

    def publish(self, type_: str, data: dict[str, Any]) -> None:
        with self._cond:
            self._seq += 1
            self._events.append(Event(self._seq, type_, data))
            self._cond.notify_all()

    def wait_for(self, after_seq: int, timeout: float) -> list[Event]:
        """Return events newer than after_seq, waiting up to timeout for one."""
        with self._cond:
            if self._seq <= after_seq and not self._closed:
                self._cond.wait(timeout)
            return [event for event in self._events if event.seq > after_seq]

    def close(self) -> None:
        """Wake every listener so the app can shut down quickly."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed
