"""Small helpers shared by the importers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.db.items_repo import NewItem


@dataclass
class ParseResult:
    """What one importer found in an export."""

    platform: str
    items: list[NewItem] = field(default_factory=list)
    # Plain-English remarks shown after the import, e.g. "skipped 3 likes".
    notes: list[str] = field(default_factory=list)
    # Names of the platform's own collections/playlists that were found.
    collections: list[str] = field(default_factory=list)


class Collector:
    """Gathers the items of one platform, merging repeats of the same link.

    The same post often shows up twice in one export (e.g. in "saved
    posts" and again in a collection). Repeats fill in each other's blanks,
    keep the earliest saved date, and add up their collections.
    """

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self._items: dict[str, NewItem] = {}
        self._collections: dict[str, list[str]] = {}
        self.notes: list[str] = []

    def add(
        self,
        url: str,
        external_id: str | None = None,
        author: str | None = None,
        caption: str | None = None,
        saved_at: str | None = None,
        collection: str | None = None,
    ) -> None:
        item = self._items.get(url)
        if item is None:
            item = NewItem(platform=self.platform, url=url)
            self._items[url] = item
            self._collections[url] = []
        item.external_id = item.external_id or external_id
        item.author = item.author or (author.strip() if author else None) or None
        item.caption = item.caption or (caption.strip() if caption else None) or None
        if saved_at and (item.saved_at is None or saved_at < item.saved_at):
            item.saved_at = saved_at
        names = self._collections[url]
        if collection and collection.strip() and collection.strip() not in names:
            names.append(collection.strip())

    def __len__(self) -> int:
        return len(self._items)

    def result(self) -> ParseResult:
        all_names: list[str] = []
        for url, item in self._items.items():
            names = self._collections[url]
            item.platform_collection = ", ".join(names) if names else None
            all_names.extend(name for name in names if name not in all_names)
        return ParseResult(self.platform, list(self._items.values()), self.notes, all_names)


def plural(count: int, word: str, many: str | None = None) -> str:
    """plural(1, "video") -> "1 video"; plural(3, "video") -> "3 videos"."""
    return f"{count:,} {word if count == 1 else (many or word + 's')}"


def iso_from_timestamp(value: Any) -> str | None:
    """Unix seconds (as Meta exports use) -> '2024-01-01T00:00:00Z'."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",  # TikTok
    "%Y-%m-%dT%H:%M:%S%z",  # YouTube (new)
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S %Z",  # YouTube (old): "2019-05-01 10:00:00 UTC"
    "%Y-%m-%d",
)


def iso_from_text(value: str | None) -> str | None:
    """A date written as text -> '2024-01-01T00:00:00Z' (assumed UTC)."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00") if value.strip().endswith("Z") else value.strip()
    for fmt in _DATE_FORMATS:
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def fix_meta_text(value: Any) -> str | None:
    """Repair text from Meta (Instagram/Facebook) exports.

    Meta writes UTF-8 letters as if each byte were its own character, so
    "café" shows up as "cafÃ©". Turning those characters back into bytes
    and reading them as UTF-8 gives the real text.
    """
    if not isinstance(value, str):
        return None
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value  # it was fine already


def walk(node: Any) -> Iterator[Any]:
    """Every value inside a JSON structure, the structure itself first."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def find_key(node: Any, wanted: str) -> Iterator[Any]:
    """Values of every key named `wanted` (any upper/lower case), at any depth."""
    wanted = wanted.lower()
    for value in walk(node):
        if isinstance(value, dict):
            for key, inner in value.items():
                if key.lower() == wanted:
                    yield inner


def get_ci(entry: dict[str, Any], *names: str) -> Any:
    """entry[name] trying each name, ignoring upper/lower case."""
    lowered = {key.lower(): value for key, value in entry.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None
