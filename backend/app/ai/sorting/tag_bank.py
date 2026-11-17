"""Words for tagging: a bank of broad, common tags the AI picks from, the
video's own hashtags as candidates, and the rules that keep tags short.

Tags used to come out too specific ("creamy tomato pasta recipe"), so the
list grew long and nothing shared a tag. A tag should be a word someone
browses by: "pasta", "london", "gym".
"""

from __future__ import annotations

import re

MAX_WORDS = 2
MAX_LENGTH = 24

# Broad tags most libraries of saved videos need. The AI prefers the user's
# own tags, then the video's hashtags, then these, before making a new word.
TAG_BANK: tuple[str, ...] = (
    # food
    "food", "recipe", "dinner", "breakfast", "lunch", "dessert", "baking", "snack", "drinks", "coffee",
    "healthy", "vegan", "protein", "meal prep", "pasta", "chicken", "restaurant", "cafe",
    # travel and places
    "travel", "hotel", "flights", "beach", "city", "hiking", "camping", "road trip", "europe", "asia",
    "london", "paris", "new york", "japan", "italy", "spain",
    # body and mind
    "fitness", "gym", "workout", "running", "yoga", "abs", "legs", "stretching", "weight loss", "health",
    "sleep", "mental health", "mindset", "motivation", "habits", "productivity",
    # learning, work and money
    "study", "school", "exams", "career", "money", "saving", "investing", "business", "side hustle",
    "language", "science", "history", "news",
    # style and home
    "shopping", "fashion", "outfit", "shoes", "skincare", "makeup", "hair", "nails", "beauty",
    "home", "decor", "cleaning", "organising", "diy", "garden", "furniture",
    # tech and making
    "tech", "phone", "apps", "ai", "gaming", "pc", "coding", "gadgets", "cars",
    "photography", "editing", "design", "art", "drawing",
    # fun and people
    "music", "movies", "tv", "books", "funny", "memes", "pets", "dogs", "cats", "family", "kids",
    "relationships", "dating", "parenting", "gift ideas", "christmas", "birthday", "wedding", "party",
    "sports", "football", "basketball",
    # kinds of video
    "life hacks", "tips", "review", "tutorial",
)

# Hashtags that say nothing about the video.
JUNK = {
    "fyp", "fy", "fypage", "fypシ", "foryou", "foryoupage", "foryourpage", "viral", "viralvideo", "trending",
    "trend", "xyzbca", "xyzcba", "tiktok", "tiktokviral", "reels", "reel", "shorts", "short", "explore",
    "explorepage", "capcut", "edit", "video", "follow", "like", "share", "duet", "stitch", "pov", "ad",
    "sponsored", "greenscreen", "blowthisup", "goviral", "4u", "fypp", "parati", "pourtoi", "relatable",
}

_HASHTAG = re.compile(r"#([^\s#.,!?;:()\[\]\"']+)")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def broad_tag(value: object) -> str:
    """A tag as the app keeps it: lowercase, no "#", one or two words, not
    too long. Empty when it isn't a usable tag (a phrase, a number, junk)."""
    text = str(value).strip().lstrip("#").replace("_", " ").replace("-", " ")
    text = " ".join(text.lower().split()).strip("•.,!?:;'\" ")
    if not text or text in JUNK or text.replace(" ", "").isdigit():
        return ""
    if len(text.split()) > MAX_WORDS or len(text) > MAX_LENGTH:
        return ""
    return text


def hashtags(*texts: str | None, limit: int = 12) -> list[str]:
    """The video's own hashtags that could be tags: "#LondonEats #fyp" ->
    ["london eats"]. Junk ones are left out."""
    found: list[str] = []
    for text in texts:
        for raw in _HASHTAG.findall(text or ""):
            tag = broad_tag(_CAMEL.sub(" ", raw))
            if tag and tag not in found:
                found.append(tag)
    return found[:limit]


def instructions(most: int, existing: list[str], own_hashtags: list[str]) -> str:
    """What the AI is told about tags, the same for notes and "AI tags"."""
    lines = [
        f"- tags: {max(1, most // 2)} to {most} tags. Each tag is ONE broad, common word that someone would browse "
        'by, like "pasta", "london", "skincare" or "gym" (two words only for a fixed name such as "new york" or '
        '"meal prep"). Lowercase, no "#". Never a phrase, a description of this one video, an adjective or a number.',
        "  Choose in this order, and only go to the next when nothing fits:",
    ]
    step = 1
    if existing:
        lines.append(f"  {step}. tags the user already has (write them exactly): {', '.join(existing[:60])}")
        step += 1
    if own_hashtags:
        lines.append(f"  {step}. this video's own hashtags, when they name a real topic: {', '.join(own_hashtags)}")
        step += 1
    lines.append(f"  {step}. these common tags: {', '.join(TAG_BANK)}")
    lines.append(f"  {step + 1}. only if none of those fit, one new broad word.")
    return "\n".join(lines)
