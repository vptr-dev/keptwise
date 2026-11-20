"""Keyword search over the SQLite FTS5 index (search_fts, see migration 4).

Each hit says which parts matched (about, transcript, AI notes), shows a
short piece of text around the match with the matching words marked, and
where that piece starts in the text, so the UI can say "about 1:20 in".
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

# Marks around matching words inside snippets. Control characters never
# appear in real text, so they can't clash with what people wrote.
START, END = "\x02", "\x03"
ELLIPSIS = "…"
PARTS = ("about", "transcript", "notes")
MAX_WORDS = 8
SNIPPET_TOKENS = 18
# Little words that would match almost everything ("how to revise for
# exams" should look for "revise" and "exams"). Kept if they're all there is.
STOP_WORDS = frozenset(
    "a an and any are as at be by can did do does for from had has have how i if in is it its me my "
    "of on or so that the their them then there these this to was we were what when where which "
    "who why will with you your "
    # Questions about the saves nearly always say "saved"; it isn't a topic.
    "save saved saves".split()
)


@dataclass
class Segment:
    text: str
    hit: bool


@dataclass
class FieldMatch:
    part: str  # about, transcript, notes
    segments: list[Segment]
    start_char: int | None  # where the snippet starts in that part's text
    part_length: int


@dataclass
class KeywordHit:
    item_id: int
    rank: float  # lower is better (FTS5 bm25)
    fields: list[FieldMatch] = field(default_factory=list)
    words: list[str] = field(default_factory=list)  # the words that matched, as written in the text


def words_of(query: str) -> list[str]:
    """The search words: letters and digits only, no little filler words, at most MAX_WORDS."""
    words = [w for w in re.findall(r"\w+", query.lower()) if w.strip("_")]
    meaningful = [w for w in words if w not in STOP_WORDS]
    return (meaningful or words)[:MAX_WORDS]


def fts_query(query: str, any_word: bool = False) -> str | None:
    """Make a safe FTS5 query from what the user typed.

    Every word is quoted (so symbols can't break the query). The last word
    also matches as a start ("past" finds "pasta") once it has 3 letters,
    so results appear while typing. any_word=True: OR instead of AND.
    """
    words = words_of(query)
    if not words:
        return None
    terms = [f'"{w}"' for w in words]
    if len(words[-1]) >= 3:
        terms[-1] += "*"
    return (" OR " if any_word else " AND ").join(terms)


def split_marks(snippet: str) -> list[Segment]:
    """'a \x02b\x03 c' -> [a ][b, hit][ c]"""
    segments: list[Segment] = []
    for piece in re.split(f"({START}[^{END}]*{END})", snippet):
        if not piece:
            continue
        if piece.startswith(START):
            segments.append(Segment(piece[1:-1], True))
        else:
            segments.append(Segment(piece, False))
    return segments


def _start_of(snippet: str, full_text: str) -> int | None:
    plain = snippet.replace(START, "").replace(END, "").strip(ELLIPSIS).strip()
    if not plain:
        return None
    found = full_text.find(plain[:60])
    return found if found >= 0 else None


def keyword_search(conn: sqlite3.Connection, query: str, limit: int = 30,
                   allowed_ids: set[int] | None = None) -> list[KeywordHit]:
    """All words first; if nothing has every word, any of the words."""
    allowed = "" if allowed_ids is None else " AND rowid IN (SELECT value FROM json_each(?))"
    scope_params = () if allowed_ids is None else (json.dumps(list(allowed_ids)),)
    for any_word in (False, True):
        match = fts_query(query, any_word)
        if match is None:
            return []
        if any_word and len(words_of(query)) < 2:
            return []
        rows = conn.execute(
            f"""SELECT rowid, about, transcript, notes,
                       bm25(search_fts, 3.0, 1.0, 2.0) AS rank,
                       snippet(search_fts, 0, ?, ?, ?, {SNIPPET_TOKENS}) AS s0,
                       snippet(search_fts, 1, ?, ?, ?, {SNIPPET_TOKENS}) AS s1,
                       snippet(search_fts, 2, ?, ?, ?, {SNIPPET_TOKENS}) AS s2
                FROM search_fts WHERE search_fts MATCH ?{allowed}
                ORDER BY rank LIMIT ?""",
            (START, END, ELLIPSIS) * 3 + (match, *scope_params, limit),
        ).fetchall()
        if rows:
            return [_hit(row) for row in rows]
    return []


def _hit(row: sqlite3.Row) -> KeywordHit:
    hit = KeywordHit(item_id=int(row["rowid"]), rank=float(row["rank"]))
    seen: dict[str, None] = {}
    for number, part in enumerate(PARTS):
        snippet = row[f"s{number}"] or ""
        if START not in snippet:
            continue  # this part didn't match
        text = row[part] or ""
        segments = split_marks(snippet)
        hit.fields.append(FieldMatch(part, segments, _start_of(snippet, text), len(text)))
        for segment in segments:
            if segment.hit:
                seen.setdefault(segment.text.lower(), None)
    hit.words = list(seen)
    return hit
