"""Routes for the search bar, the similar-search index, one item's details,
and chat over the saves."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.sorting import cards_by_id
from app.db.items_repo import get_transcript
from app.library import scope
from app.search import chat
from app.search.service import HybridHit
from app.services import AppServices, services

router = APIRouter(prefix="/api")

PART_LABELS = {"about": "Caption", "transcript": "Transcript", "notes": "AI notes"}


def _seconds_at(start_char: int | None, length: int, duration: float | None) -> float | None:
    """Rough time in the video for a place in the transcript (speech is spread evenly)."""
    if start_char is None or not length or not duration:
        return None
    return round(duration * min(1.0, start_char / length), 1)


def _result(hit: HybridHit, card: dict[str, Any], only_part: str | None = None) -> dict[str, Any]:
    duration = card.get("duration_s")
    matches = []
    if hit.keyword:
        for match in hit.keyword.fields:
            if only_part and match.part != only_part:
                continue
            matches.append({
                "part": match.part,
                "label": PART_LABELS[match.part],
                "segments": [asdict(s) for s in match.segments],
                "at_seconds": _seconds_at(match.start_char, match.part_length, duration)
                if match.part == "transcript" else None,
            })
    similar = None
    if hit.similar and not only_part:
        sim = hit.similar
        similar = {
            "part": sim.part,
            "label": PART_LABELS[sim.part],
            "text": sim.text,
            "score": round(sim.score, 3),
            "at_seconds": _seconds_at(sim.start_char, sim.part_length, duration) if sim.part == "transcript" else None,
        }
    return {
        "item": card,
        "found_by": hit.sources,
        "words": hit.keyword.words if hit.keyword else [],
        "matches": matches,
        "similar": similar,
    }


@router.get("/search")
def search(
    q: str = "",
    mode: Literal["both", "words", "similar", "captions"] = "both",
    limit: int = 30,
    svc: AppServices = Depends(services),
) -> dict[str, Any]:
    query = q.strip()[:200]
    limit = max(1, min(limit, 100))
    chosen = scope.current(svc.settings)
    hits = []
    if query:
        scoped, params = scope.where(chosen, "items")
        with svc.db.connect() as conn:
            keep = {int(row["id"]) for row in conn.execute(f"SELECT id FROM items WHERE {scoped}", params)}
        hits = svc.search.hybrid(query, limit=limit * 3, allowed_ids=keep)
    if mode == "captions":  # only words found in the video's caption
        hits = [h for h in hits if h.keyword and any(f.part == "about" for f in h.keyword.fields)]
    elif mode != "both":
        wanted = "words" if mode == "words" else "similar"
        hits = [h for h in hits if wanted in h.sources]
    hits = hits[:limit]
    with svc.db.connect() as conn:
        cards = cards_by_id(conn, [h.item_id for h in hits])
    return {
        "query": query,
        "results": [
            _result(h, cards[h.item_id], "about" if mode == "captions" else None)
            for h in hits
            if h.item_id in cards
        ],
        "similar_ready": svc.search.model_ready(),
    }


@router.get("/search/status")
def search_status(svc: AppServices = Depends(services)) -> dict[str, Any]:
    svc.search.ensure_index()  # catch up quietly if anything is waiting
    return svc.search.status()


@router.post("/search/index")
def start_index(svc: AppServices = Depends(services)) -> dict[str, Any]:
    """Get videos ready for similar search (downloads the 67 MB model once if needed)."""
    svc.search.ensure_index(allow_download=True)
    return svc.search.status()


@router.get("/items/{item_id}")
def item_details(item_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        card = cards_by_id(conn, [item_id]).get(item_id)
        if card is None:
            raise HTTPException(status_code=404, detail="No such item.")
        transcript = get_transcript(conn, item_id)
    return {"item": card, "transcript": transcript["text"] if transcript else None}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatBody(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


@router.post("/chat")
def ask(body: ChatBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    history = [m.model_dump() for m in body.messages]
    if history[-1]["role"] != "user" or not history[-1]["content"].strip():
        raise HTTPException(status_code=400, detail="Type a question first.")
    reply = chat.ask(svc.db, svc.search, svc.ai, history)
    with svc.db.connect() as conn:
        cards = cards_by_id(conn, [s["item_id"] for s in reply["sources"]])
    reply["sources"] = [s | {"item": cards[s["item_id"]]} for s in reply["sources"] if s["item_id"] in cards]
    return reply
