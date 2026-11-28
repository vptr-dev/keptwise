"""Two background jobs:

- "notes": for each video, ask the AI for notes, next steps and where it
  belongs, then sort it (see decide.py).
- "sort": Re-sort. Only asks the AI where items belong, using the notes it
  already wrote. Used after changing collections or sorting settings.

The AI provider is picked when the job starts: switching provider in
Settings applies to the next job, and this one finishes on the old one.
One item's error never stops the batch, but if the AI can't be reached at
all (twice in a row), the job stops with the reason, and Resume carries on.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.base import AIError, Message, Provider
from app.ai.json_tools import chat_json
from app.ai.pictures import pictures_for
from app.ai.service import AIService
from app.ai.sorting import collections, tags
from app.ai.sorting.decide import Decision, decide, rule_hits, rule_tag_hits
from app.ai.sorting.prompts import (
    NotesAnswer,
    SortAnswer,
    TagsAnswer,
    clean_tags,
    empty_notes,
    notes_messages,
    sort_messages,
    tags_messages,
    tidy,
    with_pictures,
)
from app.ai.sorting.settings import SortingSettings, load
from app.db.connection import Database
from app.db.items_repo import decode_json_list, get_transcript, update_item
from app.db.settings_repo import SettingsRepo
from app.importers import PLATFORM_NAMES
from app.importers.common import plural
from app.jobs.runner import Handler, JobContext

T = TypeVar("T", bound=BaseModel)

# These mean the AI can't be used at all right now, so every item would fail.
STOP_CODES = {"unreachable", "bad_key", "missing_key", "missing_model", "model_missing", "rate_limited"}
STOP_AFTER = 2
CLOUD_BATCH_LIMIT = 50
EMPTY_NOTES = "The AI's notes for this one didn't make sense, so they weren't kept. Write notes again to retry."


def now_iso() -> str:
    """UTC time to the microsecond, so "sorted before this re-sort began?" is exact."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def needs_ai_work(item: dict[str, Any], task: str, started: str) -> bool:
    if item.get("deleted_at") or item.get("gone_at"):
        return False
    if task == "notes":
        return item["status"] == "enriched"
    if task == "tags":
        return item["status"] in ("enriched", "processed")
    return item["status"] == "processed" and (item.get("sorted_at") or "") < started


def make_notes_handler(db: Database, settings: SettingsRepo, ai: AIService) -> Handler:
    def run_notes(ctx: JobContext) -> dict[str, Any]:
        return Sorter(ctx, db, settings, ai).run(ctx.params.get("item_ids", []), "notes")

    return run_notes


def make_sort_handler(db: Database, settings: SettingsRepo, ai: AIService) -> Handler:
    def run_sort(ctx: JobContext) -> dict[str, Any]:
        keep = bool(ctx.params.get("keep_manual", True))
        return Sorter(ctx, db, settings, ai, keep_manual=keep).run(ctx.params.get("item_ids", []), "sort")

    return run_sort


def make_tags_handler(db: Database, settings: SettingsRepo, ai: AIService) -> Handler:
    def run_tags(ctx: JobContext) -> dict[str, Any]:
        return Sorter(ctx, db, settings, ai).run(ctx.params.get("item_ids", []), "tags")

    return run_tags


class Sorter:
    def __init__(self, ctx: JobContext, db: Database, settings_repo: SettingsRepo, ai: AIService,
                 keep_manual: bool = True) -> None:
        self.ctx = ctx
        self.db = db
        self.provider: Provider = ai.provider(ctx.params.get("provider_id"))
        self.label = f"{self.provider.info.label} · {self.provider.model}"
        self.settings: SortingSettings = load(settings_repo)
        self.keep_manual = keep_manual
        # Pictures for the AI live next to the database (thumbnails\). The first
        # time the model can't take them, they're left out for the rest of the job.
        self.pictures_folder = db.path.parent / "thumbnails"
        self.can_see = self.settings.look_at_pictures
        collections.seed_once(db, settings_repo)
        self.counts = {"sorted": 0, "unsorted": 0, "failed": 0, "skipped": 0}
        # Re-sort skips items sorted after the job was started, so Resume
        # doesn't redo them. The route saves that moment in the job.
        self.started = str(ctx.params.get("since") or now_iso())

    def _known_names(self) -> list[str]:
        """The collections the AI may use (the user can switch any off)."""
        with self.db.connect() as conn:
            return collections.names(conn, ("mine", "ai"), ai_only=True)

    def _choices(self) -> list[dict[str, str]]:
        """The same list with folders and the user's notes, for the AI."""
        with self.db.connect() as conn:
            return collections.ai_choices(conn)

    # ---------- the batch ----------

    def run(self, raw_ids: list[Any], task: str) -> dict[str, Any]:
        ids = [int(item_id) for item_id in raw_ids]
        total = len(ids)
        tagged = set(self.ctx.params.get("tagged_ids", []))
        if self.ctx.params.get("automatic") and not self.settings.auto_notes:
            return {"message": "Automatic notes are off."}
        if self.provider.info.kind == "cloud" and (
            self.ctx.params.get("cloud_model") != self.provider.model or total > CLOUD_BATCH_LIMIT
        ):
            raise AIError("Start a new batch from Sort to confirm the current cloud model and cost.", "confirm_cost")
        strikes = 0
        verb = {"notes": "Writing notes for", "tags": "Tagging"}.get(task, "Sorting")
        for done, item_id in enumerate(ids):
            self.ctx.check()
            self.ctx.progress(done, total, f"{verb} video {done + 1:,} of {total:,}…", force=True)
            item = self._item(item_id)
            if item_id in tagged or item is None or not needs_ai_work(item, task, self.started):
                self.counts["skipped"] += 1
                continue
            try:
                if task == "tags":
                    outcome = self._tags(item)
                    tagged.add(item_id)
                    self.ctx.save_params(tagged_ids=sorted(tagged))
                elif task == "notes" or not item.get("has_notes"):
                    outcome = self._notes(item)
                else:
                    outcome = self._sort(item)
                strikes = 0
            except AIError as error:
                self._record_error(item_id, str(error))
                strikes = strikes + 1 if error.code in STOP_CODES else 0
                if strikes >= STOP_AFTER:
                    raise AIError(f"Stopped: {error} Finished videos are kept; press Resume to carry on.",
                                  error.code) from error
                outcome = "failed"
            except Exception as error:  # noqa: BLE001 - one item never stops the batch
                self._record_error(item_id, f"Something went wrong: {error}")
                outcome = "failed"
            self.counts[outcome] += 1
        self.ctx.progress(total, total, "Finished", force=True)
        return self._summary(task)

    def _item(self, item_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT i.*, a.title AS notes_title, a.summary AS notes_summary, a.kind AS notes_kind,
                          a.tags AS notes_tags, a.item_id IS NOT NULL AS has_notes
                   FROM items i LEFT JOIN ai_results a ON a.item_id = i.id WHERE i.id = ?""",
                (item_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            transcript = get_transcript(conn, item_id)
        item["transcript"] = transcript["text"] if transcript else None
        item["platform_name"] = PLATFORM_NAMES.get(item["platform"], item["platform"])
        return item

    # ---------- one item ----------

    def _popular_tags(self) -> list[str]:
        """The user's most used tags, for the AI to reuse."""
        with self.db.connect() as conn:
            return [str(row["name"]) for row in conn.execute(
                "SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id = t.id WHERE it.source <> 'auto' "
                "GROUP BY t.id ORDER BY COUNT(*) DESC LIMIT 40"
            )]

    def _ask(self, item: dict[str, Any], messages: list[Message], model_cls: type[T]) -> T:
        """Ask the AI about one video, with its pictures when the model can
        see. A model that can't take pictures is asked again without them."""
        images = pictures_for(self.pictures_folder, int(item["id"]), item.get("thumbnail_path")) if self.can_see else []
        if images:
            try:
                return chat_json(self.provider, with_pictures(messages, images), model_cls)
            except AIError as error:
                if error.code in STOP_CODES:
                    raise  # not about pictures: the AI can't be reached at all
                self.can_see = False
        return chat_json(self.provider, messages, model_cls)

    def _notes(self, item: dict[str, Any]) -> str:
        names = self._known_names()
        messages = notes_messages(item, item["transcript"], self.settings, self._choices(), self._popular_tags())
        allowed = self.settings.my_tags if self.settings.tag_mode == "only_mine" else None
        answer = tidy(self._ask(item, messages, NotesAnswer), self.settings.tags_per_video, allowed)
        if empty_notes(answer):
            # Once more, plainly; if it still says it was given nothing, keep nothing.
            answer = tidy(chat_json(self.provider, messages, NotesAnswer), self.settings.tags_per_video, allowed)
            if empty_notes(answer):
                self._record_error(item["id"], EMPTY_NOTES)
                return "failed"
        decision = self._decide(item, answer, names, has_user_links=self._has_user_links(item["id"]))
        # Tags: put on straight away, or kept as suggestions to accept.
        suggested_tags = [] if self.settings.auto_tag else answer.tags
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO ai_results (item_id, category, title, summary, steps_json, tags, provider, model,
                                           confidence, kind, facts_json, suggestions_json, new_collection,
                                           tag_suggestions_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                   ON CONFLICT (item_id) DO UPDATE SET
                     category = excluded.category, title = excluded.title, summary = excluded.summary,
                     steps_json = excluded.steps_json, tags = excluded.tags, provider = excluded.provider,
                     model = excluded.model, confidence = excluded.confidence, kind = excluded.kind,
                     facts_json = excluded.facts_json, suggestions_json = excluded.suggestions_json,
                     new_collection = NULL, tag_suggestions_json = excluded.tag_suggestions_json,
                     updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
                (
                    item["id"],
                    self._category(decision),
                    answer.title,
                    answer.summary,
                    json.dumps([{"text": step, "done": False} for step in answer.steps]),
                    json.dumps(answer.tags),
                    self.provider.info.label,
                    self.provider.model,
                    decision.best_confidence,
                    answer.kind,
                    json.dumps(answer.facts),
                    json.dumps(decision.suggestions),
                    json.dumps(suggested_tags),
                ),
            )
            if self.settings.auto_tag:
                tags.replace_source(conn, item["id"], answer.tags, "ai")
            self._apply(conn, item, decision, processed=True)
        return self._outcome(item["id"])

    def _sort(self, item: dict[str, Any]) -> str:
        names = self._known_names()
        notes = {
            "title": item.get("notes_title"),
            "summary": item.get("notes_summary"),
            "kind": item.get("notes_kind"),
            "tags": decode_json_list(item.get("notes_tags")),
        }
        messages = sort_messages(item, notes, item["transcript"], self.settings, self._choices())
        answer = chat_json(self.provider, messages, SortAnswer)
        has_user = self.keep_manual and self._has_user_links(item["id"])
        decision = self._decide(item, answer, names, has_user_links=has_user)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE ai_results SET category = ?, confidence = ?, suggestions_json = ?, new_collection = NULL, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE item_id = ?",
                (self._category(decision), decision.best_confidence, json.dumps(decision.suggestions), item["id"]),
            )
            self._apply(conn, item, decision, processed=False)
        return self._outcome(item["id"])

    def _outcome(self, item_id: int) -> str:
        """sorted: it's in a collection; unsorted: it waits in Unsorted."""
        with self.db.connect() as conn:
            placed = conn.execute("SELECT 1 FROM item_collections WHERE item_id = ?", (item_id,)).fetchone()
        return "sorted" if placed else "unsorted"

    def _tags(self, item: dict[str, Any]) -> str:
        """Ask only for tags. With "Add tags automatically" on, they replace
        the AI's old tags (the user's own stay); off, they're suggestions."""
        notes = {"title": item.get("notes_title"), "summary": item.get("notes_summary")}
        with self.db.connect() as conn:
            popular = [str(row["name"]) for row in conn.execute(
                "SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id = t.id WHERE it.source <> 'auto' "
                "GROUP BY t.id ORDER BY COUNT(*) DESC LIMIT 40"
            )]
            room = tags.MAX_PER_ITEM - int(conn.execute(
                "SELECT COUNT(*) FROM item_tags WHERE item_id = ? AND source NOT IN ('auto', 'ai')", (item["id"],)
            ).fetchone()[0])
        if room <= 0:
            return "skipped"
        most = max(1, min(self.settings.tags_per_video or 6, room))
        messages = tags_messages(item, notes, item["transcript"], self.settings, popular, most)
        allowed = self.settings.my_tags if self.settings.tag_mode == "only_mine" else None
        with self.db.connect() as conn:
            if allowed is None and tags.total(conn) >= tags.MAX_TAGS:
                # No room for new tags: keep to the ones that exist.
                allowed = [str(row["name"]) for row in conn.execute("SELECT name FROM tags")]
        answer = self._ask(item, messages, TagsAnswer)
        picked = clean_tags(answer.tags, most, allowed)
        with self.db.connect() as conn:
            if self.settings.auto_tag:
                tags.replace_source(conn, item["id"], picked, "ai")
                tags.drop_unused(conn)
            else:
                conn.execute("UPDATE ai_results SET tag_suggestions_json = ? WHERE item_id = ?",
                             (json.dumps(picked), item["id"]))
        return "sorted"

    def _decide(self, item: dict[str, Any], answer: SortAnswer | NotesAnswer, names: list[str],
                has_user_links: bool) -> Decision:
        with self.db.connect() as conn:
            existing = {name.lower() for name in collections.all_names(conn)}
            linked = [link["name"] for link in collections.links_of(conn, item["id"]) if link["source"] == "platform"]
        # Rules that name a collection that's gone are skipped (never re-made).
        rules = [name for name in rule_hits(self.settings.rules, item, item["transcript"]) if name.lower() in existing]
        return decide(
            self.settings,
            names,
            answer.collections,
            rules,
            linked,
            has_user_links,
            self._blocked_names(),
        )

    def _blocked_names(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT name FROM collections WHERE ai_allowed = 0").fetchall()
        return [str(row["name"]) for row in rows]

    def _has_user_links(self, item_id: int) -> bool:
        with self.db.connect() as conn:
            return any(link["source"] == "user" for link in collections.links_of(conn, item_id))

    @staticmethod
    def _category(decision: Decision) -> str | None:
        if decision.links:
            return decision.links[0].name
        return decision.suggestions[0]["name"] if decision.suggestions else None

    def _apply(self, conn: Any, item: dict[str, Any], decision: Decision, processed: bool) -> None:
        keep = ("user", "platform") if self.keep_manual else ("platform",)
        collections.replace_links(conn, item["id"], decision.links, keep_sources=keep,
                                  new_parent=self._ai_folder(conn))
        tags.replace_source(conn, item["id"], rule_tag_hits(self.settings.rules, item, item["transcript"]), "rule")
        fields: dict[str, Any] = {"needs_review": 0, "review_reason": None, "sorted_at": now_iso(), "error": None}
        if processed:
            # Its notes are in: everything useful is kept here now, so it can
            # be unsaved on the platform (the Unsave page).
            fields.update(status="processed", processed_at=now_iso(), safe_to_unsave=1)
        update_item(conn, item["id"], **fields)

    def _ai_folder(self, conn: Any) -> int | None:
        """The folder new AI collections go in (Settings), if it still exists."""
        if not self.settings.ai_folder:
            return None
        row = collections.find(conn, self.settings.ai_folder)
        return int(row["id"]) if row else None

    def _record_error(self, item_id: int, message: str) -> None:
        with self.db.connect() as conn:
            update_item(conn, item_id, error=message[:500])

    def _summary(self, task: str) -> dict[str, Any]:
        counts = self.counts
        worked = counts["sorted"] + counts["unsorted"]
        parts = []
        if counts["sorted"]:
            parts.append(f"{counts['sorted']:,} sorted")
        if counts["unsorted"]:
            parts.append(f"{counts['unsorted']:,} in Unsorted with a suggestion")
        if counts["failed"]:
            parts.append(f"{counts['failed']:,} failed")
        if not parts:
            message = "Nothing to do: these videos were already done."
        elif task == "tags":
            message = f"Tagged {plural(counts['sorted'], 'video')}" + (
                f", {counts['failed']:,} failed." if counts["failed"] else "."
            )
        elif task == "notes":
            message = f"Wrote notes for {plural(worked, 'video')}: " + ", ".join(parts) + "."
        else:
            message = f"Re-sorted {plural(worked + counts['failed'], 'video')}: " + ", ".join(parts) + "."
        return {"message": message, **counts, "ai": self.label}
