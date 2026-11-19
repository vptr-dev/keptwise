"""The user's sorting choices, all changeable in Settings.

Sorting is meant to be very customizable, so every choice is a setting
here, with the recommended answer as its default.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.settings_repo import SettingsRepo

KEY = "sorting"

# What kind of video it is. Decides what the notes and steps look like.
KINDS = ("recipe", "travel", "workout", "product", "diy", "learning", "entertainment", "other")

KIND_LABELS = {
    "recipe": "Recipe",
    "travel": "Place or trip",
    "workout": "Workout",
    "product": "Product",
    "diy": "DIY or how-to",
    "learning": "Tip or lesson",
    "entertainment": "Just for fun",
    "other": "Anything else",
}

# What each kind of video turns into. The user can rewrite these.
DEFAULT_KIND_STEPS = {
    "recipe": "Key details: the ingredients with amounts. Steps: the cooking steps in order.",
    "travel": "Key details: each place named, the city or area, prices and opening times if said. "
              "Steps: what to book, plan or visit.",
    "workout": "Key details: each exercise with its sets, reps or time. Steps: the workout in order.",
    "product": "Key details: the product names, prices and where to buy, as said in the video. "
               "Steps: what to check or compare before buying.",
    "diy": "Key details: the tools and materials. Steps: the instructions in order.",
    "learning": "Key details: the main ideas or tips. Steps: how to put them into practice.",
    "entertainment": "Key details: what it is (song, show, game, creator). Steps: usually none.",
    "other": "Key details: the main points. Steps: up to 3 useful next actions, or none.",
}

# The AI only ever picks from the user's own collections. (Older versions
# could also suggest new names; saved settings with that are read as this.)
Mode = Literal["my_list"]
MAX_TAGS_PER_VIDEO = 10


class Rule(BaseModel):
    """'Anything from @creator goes to Recipes', 'anything mentioning Japan
    goes to Japan trip', or 'anything mentioning pasta gets the tag #pasta'.
    A rule names a collection, a tag, or both."""

    field: Literal["author", "text"]
    value: str = Field(min_length=1, max_length=200)
    collection: str = Field(default="", max_length=80)
    tag: str = Field(default="", max_length=40)

    @field_validator("value")
    @classmethod
    def _strip_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("can't be empty")
        return value

    @field_validator("collection", "tag")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _has_a_target(self) -> "Rule":
        if not self.collection and not self.tag:
            raise ValueError("A rule needs a collection or a tag.")
        return self


class SortingSettings(BaseModel):
    # Write notes by themselves as soon as a transcripts job ends (local AI
    # only: a cloud AI costs money, so it always waits to be asked).
    auto_notes: bool = False
    # 0. When the AI writes a save's notes, does it also put it in the
    #    collection that fits best? Off (the default): its pick is only a
    #    suggestion, shown in Unsorted for you to accept or change. Your own
    #    rules and linked platform collections apply either way.
    auto_sort: bool = False
    # 1. Where items go (see Mode).
    mode: Mode = "my_list"
    # 2. The names of the platform collections a save was in (TikTok,
    #    Instagram, ...): shown to the AI as a hint, or not. Linking them to
    #    the app's collections is done on the Collections screen.
    platform_collections: Literal["hint", "ignore"] = "hint"
    # 3. How many collections one item can be in (1 = just one).
    max_collections: int = Field(default=2, ge=1, le=3)
    # 4. The user's own rules, checked before the AI.
    rules: list[Rule] = Field(default_factory=list, max_length=200)
    # 5. With auto_sort on, picks below this certainty stay in Unsorted as a
    #    suggestion instead of being filed. The AI
    #    rates fits clear 0.95 / likely 0.75 / maybe 0.5 / guess 0.25, so
    #    0.6 = file "clear" and "likely" ones, ask about "maybe" and "guess".
    review_below: float = Field(default=0.6, ge=0.0, le=1.0)
    # 6. What each kind of video turns into.
    kind_steps: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_KIND_STEPS))
    # New collections the AI makes (or ideas you approve) go in this folder.
    # Empty: at the top of the sidebar.
    ai_folder: str = Field(default="", max_length=80)

    # The AI also looks at pictures from the video (stills, or its cover),
    # not only the caption and transcript. Needs a model that can see; one
    # that can't is noticed and the pictures are left out.
    look_at_pictures: bool = True

    # Tags
    # Does the AI tag a save when it writes its notes? Off (the default): its
    # tags are suggestions you accept with one click. Your rules' tags are
    # added either way.
    auto_tag: bool = False
    # How many tags the AI writes for each video (0 = none).
    tags_per_video: int = Field(default=6, ge=0, le=MAX_TAGS_PER_VIDEO)
    # free: any words; prefer_mine: use my tags when they fit, others too;
    # only_mine: only tags from my list.
    tag_mode: Literal["free", "prefer_mine", "only_mine"] = "free"
    my_tags: list[str] = Field(default_factory=list, max_length=300)
    # 7. Duplicates across platforms are kept as separate items for now
    #    (only TikTok has been imported); not a setting yet.

    @field_validator("mode", mode="before")
    @classmethod
    def _old_mode(cls, value: object) -> object:
        return "my_list"

    @field_validator("platform_collections", mode="before")
    @classmethod
    def _old_platform(cls, value: object) -> object:
        return "hint" if value == "keep" else value

    @field_validator("tags_per_video", mode="before")
    @classmethod
    def _cap_tags(cls, value: object) -> object:
        return min(value, MAX_TAGS_PER_VIDEO) if isinstance(value, int) else value

    @field_validator("my_tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for tag in value:
            cleaned = " ".join(str(tag).strip().lstrip("#").split()).lower()[:40]
            if cleaned and cleaned not in out:
                out.append(cleaned)
        return out

    @field_validator("kind_steps")
    @classmethod
    def _known_kinds(cls, value: dict[str, str]) -> dict[str, str]:
        merged = dict(DEFAULT_KIND_STEPS)
        for kind, text in value.items():
            if kind in KINDS and text.strip():
                merged[kind] = text.strip()[:600]
        return merged


def load(settings: SettingsRepo) -> SortingSettings:
    return _parse(settings.get(KEY, {}))


def _parse(raw: Any) -> SortingSettings:
    try:
        return SortingSettings.model_validate(raw or {})
    except ValueError:
        return SortingSettings()  # a broken saved value never stops the app


def save(settings: SettingsRepo, value: SortingSettings) -> None:
    settings.set(KEY, value.model_dump())


def update(settings: SettingsRepo, changes: dict[str, Any]) -> dict[str, Any]:
    unknown = changes.keys() - SortingSettings.model_fields.keys()
    if unknown:
        raise ValueError("Unknown sorting setting.")
    return settings.update(KEY, lambda raw: _merge(_parse(raw), changes))


def _merge(current: SortingSettings, changes: dict[str, Any]) -> dict[str, Any]:
    values = current.model_dump() | changes
    if isinstance(changes.get("kind_steps"), dict):
        values["kind_steps"] = current.kind_steps | changes["kind_steps"]
    return SortingSettings.model_validate(values).model_dump()
