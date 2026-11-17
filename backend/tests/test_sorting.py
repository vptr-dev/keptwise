"""Tests for the sorting building blocks: decisions, rules, settings, prompts, collections."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.sorting import collections
from app.ai.sorting.collections import Link
from app.ai.sorting.decide import decide, platform_names, rule_hits
from app.ai.sorting.prompts import CollectionPick, NotesAnswer, notes_messages, sort_messages, tidy
from app.ai.sorting.settings import DEFAULT_KIND_STEPS, Rule, SortingSettings, load, save
from app.db.connection import Database
from app.db.items_repo import NewItem, upsert_item
from app.db.settings_repo import SettingsRepo

NAMES = ["Cooking", "Want to go", "Technology", "Electronics", "Music"]


def pick(name: str, fit: str) -> CollectionPick:
    return CollectionPick(name=name, fit=fit)  # type: ignore[arg-type]


def run(settings: SortingSettings | None = None, picks: list[CollectionPick] | None = None,
        idea: str | None = None, rules: list[str] | None = None, platform: list[str] | None = None,
        user: bool = False):
    return decide(settings or SortingSettings(), NAMES, picks or [], idea, rules or [], platform or [], user)


# ---------- decide ----------


def test_a_confident_pick_is_filed() -> None:
    decision = run(picks=[pick("cooking", "clear")])  # names match whatever the case
    assert decision.links == [Link("Cooking", "ai", 0.95, "mine")]
    assert not decision.needs_review and decision.reason is None
    assert decision.suggestions == [{"name": "Cooking", "confidence": 0.95}]


def test_an_unsure_pick_waits_for_review() -> None:
    decision = run(picks=[pick("Music", "maybe")])
    assert decision.links == []
    assert decision.needs_review
    assert decision.reason == "Not sure where this goes. The AI's best guess is Music (“maybe”)."


def test_the_review_threshold_is_the_users_choice() -> None:
    assert not run(SortingSettings(review_below=0.4), picks=[pick("Music", "maybe")]).needs_review
    assert run(SortingSettings(review_below=0.9), picks=[pick("Music", "likely")]).needs_review


def test_ideas_for_new_collections_wait_for_approval() -> None:
    decision = run(picks=[pick("Music", "guess")], idea="Car stuff")
    assert decision.needs_review and decision.new_collection == "Car stuff"
    assert decision.reason == "The AI suggests a new collection: “Car stuff”. Closest in your list: Music."
    # A name that isn't in the list counts as an idea too.
    assert run(picks=[pick("Watch later", "clear")]).new_collection == "Watch later"


def test_only_my_list_never_suggests_new_ones() -> None:
    decision = run(SortingSettings(mode="my_list"), picks=[pick("Watch later", "clear")], idea="Cars")
    assert decision.new_collection is None and decision.needs_review
    assert decision.reason == "The AI couldn't match it to any of your collections."


def test_the_ai_never_makes_collections_by_itself() -> None:
    # The old "AI decides" setting now means "my list, plus ideas I approve".
    settings = SortingSettings.model_validate({"mode": "ai_decides"})
    assert settings.mode == "my_list_plus_ideas"
    decision = run(settings, picks=[pick("Car stuff", "likely")])
    assert decision.links == [] and decision.needs_review and decision.new_collection == "Car stuff"


def test_extra_collections_need_the_ai_to_be_very_sure() -> None:
    two = run(picks=[pick("Electronics", "clear"), pick("Technology", "clear"), pick("Music", "likely")])
    assert [link.name for link in two.links] == ["Electronics", "Technology"]
    maybe = run(picks=[pick("Electronics", "clear"), pick("Technology", "likely")])
    assert [link.name for link in maybe.links] == ["Electronics"]
    one = run(SortingSettings(max_collections=1), picks=[pick("Electronics", "clear"), pick("Technology", "clear")])
    assert [link.name for link in one.links] == ["Electronics"]


def test_rules_and_platform_collections_come_first() -> None:
    decision = run(picks=[pick("Music", "guess")], rules=["Japan trip"], platform=["Pasta ideas"])
    assert decision.links == [Link("Japan trip", "rule", 1.0, "mine"), Link("Pasta ideas", "platform", None, "platform")]
    assert not decision.needs_review


def test_the_users_own_choice_stops_the_ai_adding_more() -> None:
    decision = run(picks=[pick("Cooking", "clear")], user=True)
    assert decision.links == [] and not decision.needs_review


def test_rules_match_creators_and_whole_words() -> None:
    rules = [
        Rule(field="author", value="@Pasta.Chef", collection="Cooking"),
        Rule(field="text", value="Japan", collection="Japan trip"),
        Rule(field="text", value="tokyo", collection="Japan trip"),
    ]
    item = {"author": "pasta.chef", "description": "Best ramen in Japan!"}
    assert rule_hits(rules, item, "we went to tokyo") == ["Cooking", "Japan trip"]
    assert rule_hits(rules, {"author": "x", "description": "Japanese food"}, None) == []


def test_platform_names_are_split() -> None:
    assert platform_names({"platform_collection": "Recipes 🍝, Japan trip"}) == ["Recipes 🍝", "Japan trip"]
    assert platform_names({"platform_collection": None}) == []


# ---------- settings ----------


def test_settings_defaults_are_the_recommended_answers(tmp_path: Path) -> None:
    repo = SettingsRepo(Database(tmp_path / "x.db"))
    settings = load(repo)
    assert settings.mode == "my_list_plus_ideas"
    assert settings.platform_collections == "hint"
    assert SortingSettings.model_validate({"platform_collections": "keep", "tags_per_video": 15}).tags_per_video == 10
    assert settings.max_collections == 2
    assert settings.review_below == 0.6
    assert settings.safe_to_unsave == "processed"
    assert settings.kind_steps == DEFAULT_KIND_STEPS

    settings.rules.append(Rule(field="text", value="Japan", collection="Japan trip"))
    settings.kind_steps = {"recipe": "Just the ingredients.", "spaceship": "ignored"}
    save(repo, SortingSettings.model_validate(settings.model_dump()))
    again = load(repo)
    assert again.rules[0].collection == "Japan trip"
    assert again.kind_steps["recipe"] == "Just the ingredients."
    assert "spaceship" not in again.kind_steps and again.kind_steps["travel"] == DEFAULT_KIND_STEPS["travel"]

    repo.set("sorting", {"mode": "nonsense"})
    assert load(repo).mode == "my_list_plus_ideas"  # a broken value falls back to the defaults


# ---------- prompts ----------


def test_the_notes_question_has_everything_the_ai_needs() -> None:
    item = {"platform": "tiktok", "platform_name": "TikTok", "author": "pasta.chef", "duration_s": 46,
            "description": "Easy carbonara #pasta", "platform_collection": "Recipes"}
    text = notes_messages(item, "", SortingSettings(), NAMES)[1]["content"]
    assert "Creator: @pasta.chef" in text and "Length: 0:46" in text
    assert "Transcript: (no speech, probably just music; use the caption)" in text
    assert "- Want to go" in text and "1 to 2 collections" in text and '"maybe"' in text
    assert DEFAULT_KIND_STEPS["recipe"] in text
    assert "saved it in their TikTok collection: Recipes" in text
    assert "new_collection" in text

    hidden = notes_messages(item, None, SortingSettings(platform_collections="ignore", mode="my_list"), NAMES)
    assert "Recipes" not in hidden[1]["content"].split("HOW TO SORT")[0]
    assert "Transcript: (not available)" in hidden[1]["content"]
    assert 'Set "new_collection" to null.' in hidden[1]["content"]


def test_the_sort_question_reuses_the_notes() -> None:
    item = {"platform": "tiktok", "description": "x", "author": "a"}
    text = sort_messages(item, {"title": "Carbonara", "summary": "A quick pasta.", "kind": "recipe",
                                "tags": ["pasta"]}, "long " * 2000, SortingSettings(), NAMES)[1]["content"]
    assert "Notes already written: Carbonara. A quick pasta." in text and "Tags: pasta" in text
    assert len(text) < 3000  # a short transcript excerpt only


def test_answers_are_tidied() -> None:
    answer = tidy(NotesAnswer(title="  A   title ", summary=" s ", kind="Recipe", facts=["- a", "a", "b"],
                              steps=[" • boil "] * 2, tags=["#Pasta", "pasta", "x", "y", "z", "w", "v"],
                              collections=[pick("Cooking", "clear")]))
    assert answer.title == "A title" and answer.kind == "recipe"
    assert answer.facts == ["a", "b"] and answer.steps == ["boil"]
    assert answer.tags == ["pasta", "x", "y", "z", "w", "v"][:6] and len(answer.tags) == 6
    assert tidy(NotesAnswer(title="t", summary="s", kind="weird", collections=[pick("x", "clear")])).kind == "other"


def test_an_answer_must_pick_a_collection() -> None:
    with pytest.raises(ValueError):
        NotesAnswer(title="t", summary="s", kind="other", collections=[])


# ---------- collections ----------


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "saves.db")


def test_collection_names_are_unique_whatever_the_case(db: Database) -> None:
    with db.connect() as conn:
        first = collections.ensure(conn, "Cooking")
        assert collections.ensure(conn, "  cooking ") == first
        with pytest.raises(ValueError, match="already a collection"):
            collections.create(conn, "COOKING")
        other = collections.create(conn, "Idea", origin="ai")
        with pytest.raises(ValueError):
            collections.rename(conn, other, "cooking")
        collections.rename(conn, other, "Car stuff")
        renamed = collections.find(conn, "car stuff")
        assert renamed is not None and renamed["origin"] == "mine"  # renaming an AI idea makes it yours


def test_relinking_keeps_the_users_choices(db: Database) -> None:
    with db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem(platform="tiktok", url="u1"))
        mine = collections.ensure(conn, "Mine")
        for name in ("Cooking", "Pasta", "Music"):
            collections.ensure(conn, name)
        collections.add_by_user(conn, item_id, mine)
        collections.replace_links(conn, item_id, [Link("Cooking", "ai", 0.9), Link("Pasta", "platform", None, "platform"),
                                                  Link("Not a collection", "ai", 0.9)])
        assert {(l["name"], l["source"]) for l in collections.links_of(conn, item_id)} == {
            ("Mine", "user"), ("Cooking", "ai"), ("Pasta", "platform")}
        assert collections.find(conn, "Not a collection") is None  # never made by itself
        collections.replace_links(conn, item_id, [Link("Music", "ai", 0.7)])
        assert {l["name"] for l in collections.links_of(conn, item_id)} == {"Mine", "Music"}

        conn.execute("UPDATE items SET needs_review = 1 WHERE id = ?", (item_id,))
        music = collections.find(conn, "Music")["id"]  # type: ignore[index]
        collections.move(conn, item_id, music, collections.ensure(conn, "Cooking"))
        links = {l["name"]: l["source"] for l in collections.links_of(conn, item_id)}
        assert links == {"Mine": "user", "Cooking": "user"}
        assert conn.execute("SELECT needs_review FROM items WHERE id = ?", (item_id,)).fetchone()[0] == 0
        counts = {c["name"]: c["count"] for c in collections.list_all(conn)}
        assert counts["Cooking"] == 1 and counts["Music"] == 0


def test_the_list_starts_with_broad_topics_once(db: Database) -> None:
    repo = SettingsRepo(db)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (kind, title, status, result_json) VALUES ('import', 'Import', 'done', ?)",
            ('{"platforms": [{"platform": "tiktok", "collections": ["Mindset", "Gym"]}]}',),
        )
    collections.seed_once(db, repo)
    with db.connect() as conn:
        # Platform names are linked on the Collections screen, not copied.
        assert collections.names(conn) == collections.STARTER_COLLECTIONS
        assert collections.names_from_imports(conn) == [("tiktok", "Mindset"), ("tiktok", "Gym")]
        conn.execute("DELETE FROM collections")
    collections.seed_once(db, repo)  # deleted ones don't come back
    with db.connect() as conn:
        assert collections.names(conn) == []


def test_without_platform_collections_a_starter_list_is_used(tmp_path: Path) -> None:
    db = Database(tmp_path / "other.db")
    collections.seed_once(db, SettingsRepo(db))
    with db.connect() as conn:
        assert collections.names(conn) == collections.STARTER_COLLECTIONS
