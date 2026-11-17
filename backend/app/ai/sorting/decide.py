"""Decide which collections one item goes in. No AI calls, no database:
just the user's settings applied to what we know.

Order of trust:
1. Where the user put it themselves (never changed by the app).
2. The user's own rules ("anything from @x goes to Recipes").
3. The user's links from platform collections (TikTok "recipes" -> Food).
4. The AI's picks that are certain enough (review_below). The AI rates each
   pick "clear", "likely", "maybe" or "guess" (prompts.FIT_SCORES). Extra
   collections (when one item may be in several) need a "clear" fit
   (EXTRA_MIN), because a small model hands out second places too easily.
If none of these place the item, it waits in "Needs review".
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
    needs_review: bool
    reason: str | None
    # The AI's best guesses that match collections, best first (for the inbox).
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    new_collection: str | None = None

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
    new_collection: str | None,
    rules: list[str],
    platform: list[str],
    has_user_links: bool,
    blocked: list[str] | None = None,
) -> Decision:
    """blocked: collections the user switched off for the AI; picks of
    those are dropped, even as "new" ones."""
    by_lower = {name.lower(): name for name in known_names}
    off = {name.lower() for name in blocked or []}

    # The AI's picks, matched to real collections, best first, no repeats.
    matched: dict[str, tuple[str, float, bool]] = {}
    idea = clean_name(new_collection or "") or None
    for pick in sorted(picks, key=lambda p: p.confidence, reverse=True):
        name = clean_name(pick.name)
        confidence = min(1.0, max(0.0, float(pick.confidence)))
        if not name or name.lower() in off:
            continue
        known = by_lower.get(name.lower())
        if known:
            key, is_new = known.lower(), False
            name = known
        elif settings.mode == "ai_decides":
            key, is_new = name.lower(), True
        else:
            idea = idea or name  # a name that isn't in the list is really an idea
            continue
        if key not in matched or matched[key][1] < confidence:
            matched[key] = (name, confidence, is_new)
    ranked = sorted(matched.values(), key=lambda m: m[1], reverse=True)
    suggestions = [{"name": name, "confidence": round(conf, 2)} for name, conf, _ in ranked[:3]]

    if idea and (idea.lower() in by_lower or idea.lower() in off):
        idea = None  # not new after all
    if settings.mode != "my_list_plus_ideas":
        idea = None

    links: list[Link] = []
    taken: set[str] = set()

    def add(link: Link) -> None:
        if link.name.lower() not in taken:
            taken.add(link.name.lower())
            links.append(link)

    for name in rules:
        add(Link(name, "rule", 1.0, "mine"))
    kept_platform = platform  # already mapped to the user's collections
    for name in kept_platform:
        add(Link(name, "platform", None, "platform"))
    confident = [m for m in ranked if m[1] >= settings.review_below]
    if not has_user_links:  # the user already chose; the AI doesn't add more
        room = max(0, settings.max_collections - len(rules))
        for place, (name, conf, is_new) in enumerate(confident[:room]):
            if place > 0 and conf < max(EXTRA_MIN, settings.review_below):
                break
            add(Link(name, "ai", round(conf, 2), "ai" if is_new else "mine"))

    placed = has_user_links or bool(rules) or bool(kept_platform) or bool(confident)
    reason = None
    if not placed:
        best = f" Closest in your list: {ranked[0][0]}." if ranked else ""
        if idea:
            reason = f"The AI suggests a new collection: “{idea}”.{best}"
        elif ranked:
            reason = f"Not sure where this goes. The AI's best guess is {ranked[0][0]} (“{fit_word(ranked[0][1])}”)."
        else:
            reason = "The AI couldn't match it to any of your collections."
    return Decision(links, not placed, reason, suggestions, idea)
