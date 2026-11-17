"""What the app asks the AI, and the shape of the answer it must give.

Two questions:
- notes_messages(): the full job for one video: title, summary, kind,
  key details, next steps, tags, and which collections it belongs in.
- sort_messages(): only "which collections?", used by Re-sort. It reuses the
  notes already written, so it's shorter and quicker.

The answer models are deliberately forgiving (no strict limits), because a
small local model sometimes overshoots; tidy() trims the answer afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.base import Message
from app.ai.sorting import tag_bank
from app.ai.sorting.settings import KINDS, SortingSettings

TRANSCRIPT_CHARS = 4000
SORT_TRANSCRIPT_CHARS = 1200
MAX_FACTS = 10
MAX_STEPS = 10
MAX_TAGS = 6

SYSTEM = (
    "You help someone get value from short videos they saved on social media. "
    "Use only what the video's caption and transcript say, and what any attached pictures from it show: "
    "never invent facts, amounts, prices, names or links. "
    "Write in plain, short English, even if the video is in another language. "
    "The transcript is made by speech recognition, so it may contain mistakes or song lyrics."
)


# The AI says how well a collection fits in words: small models give every
# guess "0.9" when asked for a number, but choose between words sensibly
# (tried on gemma4:12b with the user's saves). The words become a score.
Fit = Literal["clear", "likely", "maybe", "guess"]
FIT_SCORES: dict[str, float] = {"clear": 0.95, "likely": 0.75, "maybe": 0.5, "guess": 0.25}


class CollectionPick(BaseModel):
    name: str
    fit: Fit

    @property
    def confidence(self) -> float:
        return FIT_SCORES.get(self.fit, 0.5)


class SortAnswer(BaseModel):
    # At least one pick: an empty list is the model skipping the question.
    collections: list[CollectionPick] = Field(min_length=1)
    new_collection: str | None = None


class NotesAnswer(BaseModel):
    # The order matters: models write the fields in this order, and they sort
    # much better after they've written the notes (tried on gemma4:12b).
    title: str
    summary: str
    kind: str = Field(description=" | ".join(KINDS))
    facts: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    collections: list[CollectionPick] = Field(min_length=1)
    new_collection: str | None = None


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _length(seconds: float | None) -> str:
    if not seconds:
        return "unknown"
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def with_pictures(messages: list[Message], images: Sequence[str]) -> list[Message]:
    """Attach pictures from the video to the question (the last user message)
    and tell the AI they're there."""
    if not images:
        return messages
    out = [dict(m) for m in messages]
    for message in reversed(out):
        if message["role"] == "user":
            count = len(images)
            message["content"] += (
                f"\n\nPICTURES\n{count} picture{'s' if count != 1 else ''} from the video "
                f"{'are' if count != 1 else 'is'} attached. Use what {'they show' if count != 1 else 'it shows'} too: "
                "text on the screen, the place, the dish, the product, what the person is doing. "
                "This matters most when the transcript is empty or only music."
            )
            message["images"] = list(images)
            break
    return out


def describe_video(item: dict[str, Any], transcript: str | None, settings: SortingSettings,
                   transcript_chars: int = TRANSCRIPT_CHARS) -> str:
    lines = [
        "THE VIDEO",
        f"Platform: {item.get('platform_name') or item.get('platform')}",
        f"Creator: @{str(item.get('author') or 'unknown').lstrip('@')}",
        f"Length: {_length(item.get('duration_s'))}",
    ]
    if item.get("title"):
        lines.append(f"Title: {item['title']}")
    caption = item.get("description") or item.get("caption")
    lines.append(f"Caption: {_clip(caption, 1500) or '(none)'}")
    if item.get("platform_collection") and settings.platform_collections != "ignore":
        lines.append(f"The user saved it in their {item.get('platform_name') or 'platform'} collection: "
                     f"{item['platform_collection']}")
    if transcript is None:
        lines.append("Transcript: (not available)")
    elif not transcript.strip():
        lines.append("Transcript: (no speech, probably just music; use the caption)")
    else:
        lines.append(f"Transcript: {_clip(transcript, transcript_chars)}")
    return "\n".join(lines)


def _choice_line(choice: str | dict[str, str]) -> str:
    """'- Japan trip (in Travel): videos about our trip' for the AI."""
    if isinstance(choice, str):
        return f"- {choice}"
    line = f"- {choice['name']}"
    if choice.get("folder"):
        line += f" (in {choice['folder']})"
    if choice.get("description"):
        line += f": {choice['description']}"
    return line


def sorting_instructions(settings: SortingSettings, collection_names: Sequence[str | dict[str, str]]) -> str:
    listed = "\n".join(_choice_line(choice) for choice in collection_names) or "(none yet)"
    most = settings.max_collections
    lines = [
        "HOW TO SORT IT",
        "The user's collections:",
        listed,
        f"In \"collections\", give the {'collection' if most == 1 else f'1 to {most} collections'} it fits best, "
        'best first, each with "fit": "clear" (the caption or transcript is plainly about this), '
        '"likely" (mostly about this), "maybe" (it could fit, but the video is vague or mostly about something '
        'else) or "guess" (very little to go on). Be strict: use "maybe" or "guess" whenever you are not sure.',
    ]
    if settings.mode == "ai_decides":
        lines.append(
            "You may also make up a new collection (1 to 3 words) when none of the list fits; "
            "put it in \"collections\" like the others. Set \"new_collection\" to null."
        )
    else:
        lines.append("Only use names from the list, written exactly as shown (without the folder or note).")
        if settings.mode == "my_list_plus_ideas":
            lines.append(
                "If nothing in the list fits well, still give your best guess with a low confidence, and put a "
                "short name (1 to 3 words) for a new collection that would fit in \"new_collection\". "
                "Otherwise set \"new_collection\" to null."
            )
        else:
            lines.append("Set \"new_collection\" to null.")
    return "\n".join(lines)


def tag_instructions(settings: SortingSettings, item: dict[str, Any] | None = None,
                     existing: Sequence[str] = (), most: int | None = None) -> str:
    """How to tag: broad, common words, reusing the user's tags, the video's
    own hashtags and the tag bank before making a new one."""
    most = settings.tags_per_video if most is None else most
    if most == 0:
        return "- tags: an empty list."
    if settings.my_tags and settings.tag_mode == "only_mine":
        return (f"- tags: up to {most} tags, only from this list (written exactly): "
                f"{', '.join(settings.my_tags)}. Empty if none fit.")
    mine = list(dict.fromkeys([*settings.my_tags, *existing]))
    own = tag_bank.hashtags((item or {}).get("description"), (item or {}).get("caption"))
    return tag_bank.instructions(most, mine, own)


def notes_instructions(settings: SortingSettings, item: dict[str, Any] | None = None,
                       existing_tags: Sequence[str] = ()) -> str:
    kinds = "\n".join(f"- {kind}: {settings.kind_steps.get(kind, '')}" for kind in KINDS)
    return "\n".join([
        "WHAT TO WRITE",
        "- title: a short, clear title (at most 70 characters) that says what the video is about.",
        "- summary: 1 to 3 sentences.",
        f"- kind: one of {', '.join(KINDS)}.",
        f"- facts: the key details worth keeping (at most {MAX_FACTS}).",
        f"- steps: practical next steps as short to-do items (at most {MAX_STEPS}); empty if there's nothing to do.",
        tag_instructions(settings, item, existing_tags) if settings.auto_tag else "- tags: an empty list.",
        "What facts and steps should contain depends on the kind:",
        kinds,
    ])


def notes_messages(item: dict[str, Any], transcript: str | None, settings: SortingSettings,
                   collection_names: Sequence[str | dict[str, str]],
                   existing_tags: Sequence[str] = ()) -> list[Message]:
    content = "\n\n".join([
        describe_video(item, transcript, settings),
        notes_instructions(settings, item, existing_tags),
        sorting_instructions(settings, collection_names),
    ])
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def sort_messages(item: dict[str, Any], notes: dict[str, Any], transcript: str | None,
                  settings: SortingSettings, collection_names: Sequence[str | dict[str, str]]) -> list[Message]:
    known = [
        f"Notes already written: {notes.get('title') or ''}. {notes.get('summary') or ''}",
        f"Kind: {notes.get('kind') or 'other'}. Tags: {', '.join(notes.get('tags') or [])}",
    ]
    content = "\n\n".join([
        describe_video(item, transcript, settings, SORT_TRANSCRIPT_CHARS),
        "\n".join(known),
        sorting_instructions(settings, collection_names),
    ])
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


class TagsAnswer(BaseModel):
    tags: list[str] = Field(default_factory=list)


def tags_messages(item: dict[str, Any], notes: dict[str, Any], transcript: str | None,
                  settings: SortingSettings, popular: Sequence[str], most: int) -> list[Message]:
    """Only "which tags?", for the AI tags button. Reusing the user's
    existing tags keeps the list tidy instead of growing near-duplicates."""
    lines = ["WHAT TO WRITE", tag_instructions(settings, item, popular, most)]
    lines.append('Answer as JSON: {"tags": ["...", "..."]}')
    known = f"Notes already written: {notes.get('title') or ''}. {notes.get('summary') or ''}"
    content = "\n\n".join([
        describe_video(item, transcript, settings, SORT_TRANSCRIPT_CHARS),
        known,
        "\n".join(lines),
    ])
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def clean_tags(values: list[str], limit: int, allowed: list[str] | None = None) -> list[str]:
    """Keep the AI's tags that are usable: short broad words (see tag_bank),
    or with `allowed`, only tags from that list, exactly."""
    out: list[str] = []
    for value in values:
        if allowed is not None:
            tag = " ".join(str(value).lower().lstrip("#").split())[:40]
            tag = tag if tag in allowed else ""
        else:
            tag = tag_bank.broad_tag(value)
        if tag and tag not in out:
            out.append(tag)
    return out[:limit]


def tidy(answer: NotesAnswer, max_tags: int = MAX_TAGS, allowed_tags: list[str] | None = None) -> NotesAnswer:
    """Trim an answer to sensible sizes and fix small slips. With
    allowed_tags, only tags from that list are kept."""
    def clean_list(values: list[str], limit: int) -> list[str]:
        out: list[str] = []
        for value in values:
            value = " ".join(str(value).split()).strip("-• ")
            if value and value not in out:
                out.append(value)
        return out[:limit]

    answer.title = " ".join(answer.title.split())[:90] or "Untitled video"
    answer.summary = answer.summary.strip()
    kind = answer.kind.strip().lower()
    answer.kind = kind if kind in KINDS else "other"
    answer.facts = clean_list(answer.facts, MAX_FACTS)
    answer.steps = clean_list(answer.steps, MAX_STEPS)
    answer.tags = clean_tags(answer.tags, max_tags, allowed_tags)
    return answer
