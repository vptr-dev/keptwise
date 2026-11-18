"""Chat that answers only from the user's own saves.

1. Find the saves that best match the question (the hybrid search).
2. Give the AI just those, numbered [1], [2], ... and tell it to answer
   from them only and say which numbers it used.
3. Return the answer plus the cited saves, so the UI can show them as cards.

If the search finds nothing, the AI isn't asked at all: the answer is
simply that nothing in the saves matches.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.ai.base import Message
from app.ai.service import AIService
from app.db.connection import Database
from app.db.items_repo import decode_json_list
from app.search.service import HybridHit, SearchService

MAX_SOURCES = 8
TRANSCRIPT_CHARS = 1500
HISTORY_TURNS = 6
NOTHING_FOUND = (
    "I couldn't find anything about that in your saves. Try other words, or check that the "
    "videos have transcripts (Sort page) so there's something to search."
)

SYSTEM = (
    "You answer questions about videos and posts the user saved. Use ONLY the numbered saves "
    "given to you; never add facts from your own knowledge. Cite the saves you use like [1] or "
    "[2][3] right after the sentence. If the saves don't answer the question, set found to false "
    "and say briefly that the saves don't cover it. Keep answers short and practical, with a "
    "short list when there are several items."
)


class ChatAnswer(BaseModel):
    # Field order matters for small local models: the list goes last.
    found: bool = Field(description="true if the saves answer the question")
    answer: str = Field(description="the answer, citing saves like [1]")
    sources: list[int] = Field(default_factory=list, description="numbers of the saves used")


@dataclass
class Source:
    number: int
    item_id: int
    text: str


def retrieval_query(messages: list[Message]) -> str:
    """The latest question; a short follow-up ("and the second one?") also
    gets the previous question, so the search has something to go on."""
    questions = [m["content"] for m in messages if m.get("role") == "user" and m.get("content", "").strip()]
    if not questions:
        return ""
    query = questions[-1]
    if len(query.split()) < 5 and len(questions) > 1:
        query = f"{questions[-2]} {query}"
    return query


def describe_source(conn: sqlite3.Connection, number: int, hit: HybridHit,
                    transcript_chars: int = TRANSCRIPT_CHARS) -> Source:
    """Everything the AI is told about one save: what it is, who made it,
    where the user filed it, the AI notes, and (part of) what was said."""
    row = conn.execute(
        """SELECT i.platform, i.author, i.title, i.caption, i.description, i.duration_s, i.saved_at, i.done,
                  a.title AS ai_title, a.kind, a.summary, a.facts_json, a.steps_json, t.text AS transcript
           FROM items i LEFT JOIN ai_results a ON a.item_id = i.id
           LEFT JOIN transcripts t ON t.item_id = i.id WHERE i.id = ?""",
        (hit.item_id,),
    ).fetchone()
    lines = [f"[{number}] {row['ai_title'] or row['title'] or row['caption'] or 'A saved video'}"]
    about = [f"From {row['platform']}" + (f", by @{row['author'].lstrip('@')}" if row["author"] else "")]
    if row["kind"]:
        about.append(f"kind: {row['kind']}")
    if row["duration_s"]:
        about.append(f"{round(row['duration_s'] / 60, 1)} min long")
    if row["saved_at"]:
        about.append(f"saved {str(row['saved_at'])[:10]}")
    if row["done"]:
        about.append("already done by the user")
    lines.append("; ".join(about))
    filed = [str(r["name"]) for r in conn.execute(
        "SELECT c.name FROM item_collections ic JOIN collections c ON c.id = ic.collection_id WHERE ic.item_id = ?",
        (hit.item_id,),
    )]
    if filed:
        lines.append("In the user's collections: " + ", ".join(filed))
    tag_names = [str(r["name"]) for r in conn.execute(
        "SELECT t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id WHERE it.item_id = ? AND it.source <> 'auto'",
        (hit.item_id,),
    )]
    if tag_names:
        lines.append("Tags: " + ", ".join(tag_names))
    caption = row["description"] or row["caption"]
    if caption:
        lines.append(f"Caption: {caption[:500]}")
    if row["summary"]:
        lines.append(f"AI notes: {row['summary']}")
    facts = [str(f) for f in decode_json_list(row["facts_json"])]
    if facts:
        lines.append("Key details: " + "; ".join(facts))
    steps = [s.get("text", "") if isinstance(s, dict) else str(s) for s in decode_json_list(row["steps_json"])]
    if steps:
        lines.append("Steps: " + "; ".join(steps))
    transcript = row["transcript"] or ""
    if transcript:
        start = 0
        if hit.similar and hit.similar.part == "transcript":
            start = max(0, hit.similar.start_char - 300)
        elif hit.keyword:
            starts = [f.start_char for f in hit.keyword.fields if f.part == "transcript" and f.start_char]
            start = max(0, starts[0] - 300) if starts else 0
        piece = transcript[start : start + transcript_chars]
        lines.append(f"Transcript{' (part)' if len(transcript) > len(piece) else ''}: {piece}")
    return Source(number, hit.item_id, "\n".join(lines))


def chat_messages(history: list[Message], sources: list[Source]) -> list[Message]:
    saves = "\n\n".join(source.text for source in sources)
    turns = [m for m in history if m.get("role") in ("user", "assistant")][-HISTORY_TURNS:]
    earlier = turns[:-1]
    question = turns[-1]["content"] if turns else ""
    parts = []
    if earlier:
        parts.append("Conversation so far:\n" + "\n".join(f"{m['role']}: {m['content'][:600]}" for m in earlier))
    parts.append(f"The saves you may use:\n\n{saves}")
    parts.append(f"Question: {question}")
    parts.append(
        'Answer as JSON: {"found": true or false, "answer": "...", "sources": [numbers of the saves you used]}'
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]


def cited_numbers(answer: ChatAnswer, count: int) -> list[int]:
    """The saves really cited: the list the AI gave plus any [n] in the text."""
    numbers = list(answer.sources) + [int(n) for n in re.findall(r"\[(\d+)\]", answer.answer)]
    out: list[int] = []
    for number in numbers:
        if 1 <= number <= count and number not in out:
            out.append(number)
    return out


def ask(db: Database, search: SearchService, ai: AIService, history: list[Message]) -> dict[str, Any]:
    """Answer the last question in history. Returns found, answer, and the sources used."""
    query = retrieval_query(history)
    hits = search.hybrid(query, limit=MAX_SOURCES) if query else []
    if not hits:
        return {"found": False, "answer": NOTHING_FOUND, "sources": [], "searched": query}
    ai.check_ready()
    with db.connect() as conn:
        sources = [describe_source(conn, number, hit) for number, hit in enumerate(hits, start=1)]
    answer = ai.chat_json(chat_messages(history, sources), ChatAnswer)
    numbers = cited_numbers(answer, len(sources))
    found = bool(answer.found and answer.answer.strip())
    text = answer.answer.strip() or NOTHING_FOUND
    return {
        "found": found,
        "answer": text,
        "sources": [{"number": n, "item_id": sources[n - 1].item_id} for n in numbers] if found else [],
        "searched": query,
        "model": ai.current_label(),
    }

