"""Cutting an item's text into short passages for the similar search.

Short passages work better than one long text: the model reads at most
about 400 words at once, and a passage tells us WHERE in a long
transcript the idea came up.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

WINDOW_WORDS = 70
OVERLAP_WORDS = 15
MAX_ABOUT_CHARS = 1200


@dataclass(frozen=True)
class Passage:
    part: str  # about, transcript, notes
    start_char: int
    text: str


def text_hash(parts: dict[str, str]) -> str:
    joined = "\x1f".join(parts.get(name, "") for name in ("about", "transcript", "notes"))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def split_transcript(text: str) -> list[Passage]:
    """Windows of ~70 words that overlap a little, with their start position."""
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    passages = []
    step = WINDOW_WORDS - OVERLAP_WORDS
    for first in range(0, len(words), step):
        chunk = words[first : first + WINDOW_WORDS]
        start, end = chunk[0].start(), chunk[-1].end()
        passages.append(Passage("transcript", start, text[start:end]))
        if first + WINDOW_WORDS >= len(words):
            break
    return passages


def make_passages(parts: dict[str, str]) -> list[Passage]:
    passages = []
    about = (parts.get("about") or "").strip()
    if about:
        passages.append(Passage("about", 0, about[:MAX_ABOUT_CHARS]))
    notes = (parts.get("notes") or "").strip()
    if notes:
        passages.append(Passage("notes", 0, notes[:MAX_ABOUT_CHARS]))
    passages.extend(split_transcript(parts.get("transcript") or ""))
    return passages
