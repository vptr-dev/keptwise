"""Tests for folders, tags, the "not in any collection" tag, bulk actions
and the new Library filters and sort orders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.sorting import collections, tags
from app.ai.sorting.prompts import CollectionPick, NotesAnswer, notes_messages, tidy
from app.ai.sorting.settings import Rule, SortingSettings, save
from app.ai.sorting.decide import rule_tag_hits
from app.db.connection import Database
from app.db.items_repo import NewItem, update_item, upsert_item
from app.services import AppServices


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "saves.db")


def add(svc_or_db: AppServices | Database, n: int, *, processed: bool = True, author: str | None = None,
        duration: float | None = None, saved_at: str = "2026-01-01") -> int:
    database = svc_or_db.db if isinstance(svc_or_db, AppServices) else svc_or_db
    with database.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("tiktok", f"https://example.com/v/{n}", author=author,
                                               saved_at=saved_at))
        if duration is not None:
            update_item(conn, item_id, duration_s=duration)
        if processed:
            update_item(conn, item_id, status="processed")
            conn.execute("INSERT INTO ai_results (item_id, title, steps_json) VALUES (?, ?, ?)",
                         (item_id, f"Video {n}", json.dumps([{"text": "x", "done": False}] * n)))
    return item_id


# ---------- folders ----------


def test_collections_are_one_list_of_at_most_fifty(db: Database) -> None:
    item = add(db, 1)
    with db.connect() as conn:
        travel = collections.create(conn, "Travel")
        food = collections.create(conn, "Food")
        assert [(row["name"], row["parent_id"], row["depth"]) for row in collections.list_all(conn)] == [
            ("Travel", None, 0), ("Food", None, 0)]
        collections.place(conn, food, None, 0)  # drag Food to the top
        assert [row["name"] for row in collections.list_all(conn)] == ["Food", "Travel"]
        for n in range(collections.MAX_COLLECTIONS - 2):
            collections.create(conn, f"Topic {n}")
        assert collections.room_left(conn) == 0
        with pytest.raises(ValueError, match="most a space can hold"):
            collections.create(conn, "One too many")
        assert collections.ensure(conn, "travel") == travel  # an existing one is still fine

        collections.add_by_user(conn, item, food)
        collections.merge(conn, food, travel)
        assert [link["name"] for link in collections.links_of(conn, item)] == ["Travel"]
        assert collections.find(conn, "Food") is None


def test_the_ai_only_sees_collections_it_may_use(db: Database) -> None:
    with db.connect() as conn:
        travel = collections.create(conn, "Travel")
        secret = collections.create(conn, "My own picks")
        collections.update(conn, travel, description="  the  2027 trip ")
        collections.update(conn, secret, ai_allowed=False)
        assert collections.names(conn, ("mine",), ai_only=True) == ["Travel"]
        assert collections.ai_choices(conn) == [{"name": "Travel", "folder": "", "description": "the 2027 trip"}]
        with pytest.raises(ValueError):
            collections.update(conn, travel, color="neon")
    text = notes_messages({"platform": "tiktok"}, "x", SortingSettings(), [
        {"name": "Travel", "folder": "", "description": "the 2027 trip"}])[1]["content"]
    assert "- Travel: the 2027 trip" in text


def test_a_save_has_at_most_ten_tags(db: Database) -> None:
    item = add(db, 1)
    with db.connect() as conn:
        for n in range(10):
            tags.add(conn, item, f"tag {n}")
        with pytest.raises(ValueError, match="up to 10 tags"):
            tags.add(conn, item, "eleven")
        tags.add(conn, item, "tag 3")  # one it already has is fine
        tags.sync_no_collection(conn, item, "unsorted")  # the app's own tag doesn't count
        assert "unsorted" in {t["name"] for t in tags.of_item(conn, item)}


# ---------- tags ----------


def test_tags_merge_on_rename_and_keep_the_users_own(db: Database) -> None:
    item, other = add(db, 1), add(db, 2)
    with db.connect() as conn:
        tags.replace_source(conn, item, ["#Pasta", "quick dinner"], "ai")
        tags.add(conn, item, "pasta", "user")  # the user's choice wins
        assert {(t["name"], t["source"]) for t in tags.of_item(conn, item)} == {("pasta", "user"), ("quick dinner", "ai")}
        tags.replace_source(conn, item, ["italian"], "ai")  # notes redone
        assert {t["name"] for t in tags.of_item(conn, item)} == {"pasta", "italian"}

        tags.add(conn, other, "Italian food")
        italian_food = tags.find(conn, "italian food")["id"]  # type: ignore[index]
        kept = tags.rename(conn, italian_food, "ITALIAN")  # becomes the same tag as "italian"
        assert kept == tags.find(conn, "italian")["id"]  # type: ignore[index]
        assert {t["name"]: t["count"] for t in tags.list_all(conn)}["italian"] == 2
        tags.drop_unused(conn)
        assert "quick dinner" not in {t["name"] for t in tags.list_all(conn)}


def test_saves_in_no_collection_get_the_chosen_tag(db: Database) -> None:
    lonely, filed, waiting = add(db, 1), add(db, 2), add(db, 3, processed=False)
    with db.connect() as conn:
        collections.add_by_user(conn, filed, collections.ensure(conn, "Food"))
        tags.sync_all_no_collection(conn, "unsorted")
        tagged = lambda item: [t["name"] for t in tags.of_item(conn, item)]  # noqa: E731
        assert tagged(lonely) == ["unsorted"] and tagged(filed) == [] and tagged(waiting) == []
        collections.add_by_user(conn, lonely, collections.ensure(conn, "Food"))
        tags.sync_no_collection(conn, lonely, "unsorted")
        assert tagged(lonely) == []
        tags.sync_all_no_collection(conn, "")  # switched off
        assert tags.find(conn, "unsorted") is None


def test_tag_settings_rules_and_prompts() -> None:
    with pytest.raises(ValueError):
        Rule(field="text", value="Japan")  # needs a collection or a tag
    rule = Rule(field="text", value="Japan", tag="Japan")
    assert rule_tag_hits([rule], {"description": "Ramen in Japan"}, None) == ["japan"]
    settings = SortingSettings(my_tags=["#Pasta", "pasta", " Gym  Days "], no_collection_tag="#Inbox")
    assert settings.my_tags == ["pasta", "gym days"] and settings.no_collection_tag == "inbox"

    text = notes_messages({"platform": "tiktok"}, "x", SortingSettings(tags_per_video=12, tag_mode="only_mine",
                                                                      my_tags=["pasta", "gym"]), [])[1]["content"]
    assert "up to 10 tags, only from this list (written exactly): pasta, gym" in text

    # Tags are broad, common words: the user's own first, then the video's hashtags, then the bank.
    video = {"platform": "tiktok", "caption": "Best spots #LondonEats #fyp #food #viral", "description": None}
    text = notes_messages(video, "x", SortingSettings(), [], ["pasta", "travel"])[1]["content"]
    assert "ONE broad, common word" in text
    assert "1. tags the user already has (write them exactly): pasta, travel" in text
    assert "2. this video's own hashtags, when they name a real topic: london eats, food" in text  # no #fyp, #viral
    assert "3. these common tags: food, recipe" in text
    off = notes_messages(video, "x", SortingSettings(auto_tag=False), [])[1]["content"]
    assert "- tags: an empty list." in off
    assert "- tags: an empty list." in notes_messages({}, None, SortingSettings(tags_per_video=0), [])[1]["content"]

    answer = NotesAnswer(title="t", summary="s", kind="recipe", tags=["Pasta", "cats", "gym", "x", "y"],
                         collections=[CollectionPick(name="x", fit="clear")])
    assert tidy(answer, 10, ["pasta", "gym"]).tags == ["pasta", "gym"]
    # Phrases, numbers and junk are dropped; "#" and odd spacing are tidied.
    loose = NotesAnswer(title="t", summary="s", kind="recipe", collections=[CollectionPick(name="x", fit="clear")],
                        tags=["#Pasta", "creamy tomato pasta recipe", "New  York", "meal-prep", "2024", "fyp", "pasta"])
    assert tidy(loose, 10).tags == ["pasta", "new york", "meal prep"]


# ---------- the API ----------


def test_tag_and_folder_routes(api: TestClient, svc: AppServices) -> None:
    item = add(svc, 1)
    card = api.post(f"/api/items/{item}/tags", json={"name": "#Weekend"}).json()
    assert card["tags"] == ["weekend"] and card["tag_list"][0]["source"] == "user"
    tag_id = card["tag_list"][0]["id"]
    tag = api.patch(f"/api/tags/{tag_id}", json={"name": "Saturday", "color": "teal"}).json()["tags"][0]
    assert (tag["id"], tag["name"], tag["color"], tag["count"], tag["by_user"]) == (tag_id, "saturday", "teal", 1, 1)
    assert api.delete(f"/api/items/{item}/tags/{tag_id}").json()["tags"] == []

    a = api.post("/api/tags", json={"name": "pasta"}).json()["created_id"]
    b = api.post("/api/tags", json={"name": "pastas"}).json()["created_id"]
    merged = api.post("/api/tags/merge", json={"tag_ids": [a, b], "into": "Pasta"}).json()["tags"]
    assert [t["name"] for t in merged] == ["pasta", "saturday"]  # a coloured tag stays even when unused
    left = api.post("/api/tags/delete", json={"tag_ids": [merged[0]["id"]]}).json()["tags"]
    assert [t["name"] for t in left] == ["saturday"]

    listed = api.get("/api/collections").json()
    assert listed["limit"] == 50 and listed["per_save"] == 10 and [c["name"] for c in listed["collections"]][:2] == ["Food", "Travel"]
    travel = next(c["id"] for c in listed["collections"] if c["name"] == "Travel")
    changed = api.patch(f"/api/collections/{travel}", json={"ai_allowed": False, "color": "rose", "collapsed": True,
                                                           "description": "Our trip"}).json()["collections"]
    row = next(c for c in changed if c["id"] == travel)
    assert (row["ai_allowed"], row["color"], row["description"]) == (False, "rose", "Our trip")
    api.post(f"/api/collections/{travel}/place", json={"parent_id": None, "index": 0})
    assert [c["name"] for c in api.get("/api/collections").json()["collections"]][:2] == ["Travel", "Food"]
    food = next(c["id"] for c in changed if c["name"] == "Food")
    after = api.post(f"/api/collections/{food}/merge", json={"into_id": travel}).json()["collections"]
    assert "Food" not in [c["name"] for c in after]
    for n in range(50):
        api.post("/api/collections", json={"name": f"Extra {n}"})
    full = api.post("/api/collections", json={"name": "Too many"})
    assert full.status_code == 400 and "most a space can hold" in full.json()["detail"]


def test_bulk_actions_and_new_library_filters(api: TestClient, svc: AppServices) -> None:
    save(svc.settings, SortingSettings(no_collection_tag="unsorted"))
    first = add(svc, 1, author="@Chef", duration=30, saved_at="2026-01-01")
    second = add(svc, 2, author="gym.guy", duration=90, saved_at="2026-02-01")
    third = add(svc, 3, duration=10, saved_at="2026-03-01")
    folder = api.post("/api/collections", json={"name": "Dinners"}).json()["created_id"]
    inner = api.post("/api/collections", json={"name": "Pasta"}).json()["created_id"]

    done = api.post("/api/items/bulk", json={"item_ids": [first, second], "action": "add_to", "collection_id": inner})
    assert done.json()["changed"] == 2
    api.post("/api/items/bulk", json={"item_ids": [first, second, third], "action": "add_tag", "tag": "Try"})
    api.post("/api/items/bulk", json={"item_ids": [third], "action": "done"})
    assert api.post("/api/items/bulk", json={"item_ids": [first], "action": "add_to"}).status_code == 400

    items = lambda query: [i["id"] for i in api.get(f"/api/library/items?{query}").json()["items"]]  # noqa: E731
    assert items(f"collection_id={inner}") == [second, first]
    assert items(f"collection_id={folder}") == []
    assert items("in_collection=none") == [third]
    assert items("tag=try") == [third, second, first]
    api.post("/api/items/bulk", json={"item_ids": [first], "action": "add_tag", "tag": "pasta"})
    assert items("tags=try,pasta") == [first]  # every tag listed
    assert items("q=video 2") == [second]  # words in the title, notes, ...
    assert items("creator=chef") == [first]
    assert items("sort=longest") == [second, first, third]
    assert items("sort=most_steps") == [third, second, first]
    assert items("progress=done") == [third]
    assert api.get(f"/api/library?view=collection&collection_id={inner}").json()[0]["id"] == second

    filters = api.get("/api/library/filters").json()
    assert {t["id"]: t["count"] for t in filters["tags"]} == {"try": 3, "pasta": 1}
    assert filters["no_collection"] == 1 and filters["creators"] == []

    moved = api.post("/api/items/bulk", json={"item_ids": [first], "action": "move_to", "from_id": inner,
                                              "collection_id": folder}).json()["items"][0]
    assert [c["name"] for c in moved["collections"]] == ["Dinners"]
    removed = api.post("/api/items/bulk", json={"item_ids": [first], "action": "remove_from",
                                                "collection_id": folder}).json()["items"][0]
    assert "unsorted" in removed["tags"]  # back in no collection, so it gets the tag


def test_sidebar_settings_are_saved(api: TestClient) -> None:
    ui = api.get("/api/ui").json()
    assert ui["nav_order"] == [] and ui["sidebar_collections"] and ui["card_size"] == "medium"
    api.put("/api/ui", json=ui | {"nav_order": ["/library", "/home"], "nav_hidden": ["/chat"], "card_size": "large"})
    again = api.get("/api/ui").json()
    assert again["nav_order"] == ["/library", "/home"] and again["nav_hidden"] == ["/chat"]


def test_a_save_is_in_at_most_ten_collections(db: Database) -> None:
    item = add(db, 1)
    with db.connect() as conn:
        ids = [collections.create(conn, f"Topic {n}") for n in range(12)]
        for collection_id in ids[:10]:
            collections.add_by_user(conn, item, collection_id)
        collections.add_by_user(conn, item, ids[0])  # already in it: fine
        with pytest.raises(collections.SaveFull, match="up to 10 collections"):
            collections.add_by_user(conn, item, ids[10])
        assert collections.add_from_platform(conn, item, ids[11]) is False
        collections.move(conn, item, ids[0], ids[10])  # moving out of one makes room
        assert collections.count_on(conn, item) == 10
        collections.replace_links(conn, item, [collections.Link("Topic 11", "ai")])
        assert collections.count_on(conn, item) == 10  # the user's own picks stay, the AI's is left out


def test_the_app_has_at_most_a_hundred_tags(db: Database) -> None:
    item = add(db, 1)
    with db.connect() as conn:
        for n in range(tags.MAX_TAGS):
            tags.ensure(conn, f"tag{n}")
        with pytest.raises(tags.TagsFull, match="100 tags"):
            tags.add(conn, item, "brand new")
        tags.add(conn, item, "tag5")  # one that exists is fine
        tags.replace_source(conn, item, ["new one", "tag7"], "ai")  # new words are skipped, not the rest
        assert sorted(t["name"] for t in tags.of_item(conn, item)) == ["tag5", "tag7"]
        tags.sync_no_collection(conn, item, "unsorted")  # the app's own tag still works


def test_bulk_add_tag_says_when_the_tag_list_is_full(api: TestClient, svc: AppServices) -> None:
    item = add(svc, 1)
    with svc.db.connect() as conn:
        for n in range(tags.MAX_TAGS):
            tags.ensure(conn, f"tag{n}")
    response = api.post("/api/items/bulk", json={"item_ids": [item], "action": "add_tag", "tag": "brand new"})
    assert response.status_code == 400
    assert "100 tags" in response.json()["detail"]
    listed = api.get("/api/tags").json()
    assert (listed["limit"], listed["total"], listed["per_save"]) == (100, 100, 10)
