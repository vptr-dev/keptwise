"""Decide which collections one item goes in. No AI calls, no database:
just the user's settings applied to what we know.

Order of trust:
1. Where the user put it themselves (never changed by the app).
2. The user's own rules ("anything from @x goes to Recipes").
3. The user's links from platform collections (TikTok "recipes" -> Food).
4. Only when "Put into collections automatically" is on: the AI's picks
   that are certain enough (review_below). The AI rates each pick "clear",
   "likely", "maybe" or "guess" (prompts.FIT_SCORES). Extra collections
   (when one item may be in several) need a "clear" fit (EXTRA_MIN),
   because a small model hands out second places too easily.
A save none of these place stays in Unsorted, with the AI's best pick shown
as a suggestion for the user to accept or change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.sorting.collections import Link, clean_name
from app.ai.sorting.prompts import CollectionPick
from app.ai.sorting.settings import Rule, SortingSettings

EXTRA_MIN = 0.85


@dataclass
class Decision:
    links: list[Link]
    # The AI's best guesses that match collections, best first. Shown in
    # Unsorted when the save isn't in a collection, to accept with a click.
    suggestions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def best_confidence(self) -> float | None:
        return self.suggestions[0]["confidence"] if self.suggestions else None


def rule_hits(rules: list[Rule], item: dict[str, Any], transcript: str | None) -> list[str]:
    """Collections the user's rules send this item to."""
    author = str(item.get("author") or "").lstrip("@").lower()
    text = " ".join(
        str(part or "") for part in (item.get("title"), item.get("description"), item.get("caption"), transcript)
    ).lower()
    hits: list[str] = []
    for rule in rules:
        value = rule.value.strip().lower()
        if rule.field == "author":
            matched = author == value.lstrip("@")
        else:
            matched = re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text) is not None
        if matched and rule.collection and rule.collection.lower() not in {hit.lower() for hit in hits}:
            hits.append(clean_name(rule.collection))
    return hits


def _rule_matches(rule: Rule, author: str, text: str) -> bool:
    value = rule.value.strip().lower()
    if rule.field == "author":
        return author == value.lstrip("@")
    return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text) is not None


def rule_tag_hits(rules: list[Rule], item: dict[str, Any], transcript: str | None) -> list[str]:
    """Tags the user's rules give this item."""
    author = str(item.get("author") or "").lstrip("@").lower()
    text = " ".join(
        str(part or "") for part in (item.get("title"), item.get("description"), item.get("caption"), transcript)
    ).lower()
    hits: list[str] = []
    for rule in rules:
        if rule.tag and _rule_matches(rule, author, text) and rule.tag.lower() not in hits:
            hits.append(rule.tag.lower())
    return hits


def platform_names(item: dict[str, Any]) -> list[str]:
    """The importer joins several platform collections with ', '."""
    raw = str(item.get("platform_collection") or "")
    return [clean_name(name) for name in raw.split(", ") if clean_name(name)]


def fit_word(confidence: float) -> str:
    """The AI's own word for a score (see prompts.FIT_SCORES)."""
    if confidence >= 0.9:
        return "clear"
    if confidence >= 0.7:
        return "likely"
    return "maybe" if confidence >= 0.45 else "guess"


def decide(
    settings: SortingSettings,
    known_names: list[str],
    picks: list[CollectionPick],
    rules: list[str],
    platform: list[str],
    has_user_links: bool,
    blocked: list[str] | None = None,
) -> Decision:
    """blocked: collections the user switched off for the AI; picks of
    those are dropped. Picks that aren't one of the user's collections are
    dropped too: the AI never makes collections."""
    by_lower = {name.lower(): name for name in known_names}
    off = {name.lower() for name in blocked or []}

    # The AI's picks, matched to real collections, best first, no repeats.
    matched: dict[str, tuple[str, float]] = {}
    for pick in sorted(picks, key=lambda p: p.confidence, reverse=True):
        known = by_lower.get(clean_name(pick.name).lower())
        if not known or known.lower() in off:
            continue
        confidence = min(1.0, max(0.0, float(pick.confidence)))
        if known.lower() not in matched or matched[known.lower()][1] < confidence:
            matched[known.lower()] = (known, confidence)
    ranked = sorted(matched.values(), key=lambda m: m[1], reverse=True)
    suggestions = [{"name": name, "confidence": round(conf, 2)} for name, conf in ranked[:3]]

    links: list[Link] = []
    taken: set[str] = set()

    def add(link: Link) -> None:
        if link.name.lower() not in taken:
            taken.add(link.name.lower())
            links.append(link)

    for name in rules:
        add(Link(name, "rule", 1.0, "mine"))
    for name in platform:  # already mapped to the user's collections
        add(Link(name, "platform", None, "platform"))
    if settings.auto_sort and not has_user_links:  # the user already chose; the AI doesn't add more
        confident = [m for m in ranked if m[1] >= settings.review_below]
        room = max(0, settings.max_collections - len(rules))
        for place, (name, conf) in enumerate(confident[:room]):
            if place > 0 and conf < max(EXTRA_MIN, settings.review_below):
                break
            add(Link(name, "ai", round(conf, 2), "mine"))
    return Decision(links, suggestions)
