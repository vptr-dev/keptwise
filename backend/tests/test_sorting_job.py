"""Tests for the AI notes and re-sort jobs and their routes, using the real
AI layer talking to a fake Ollama (tests/fakes.py)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.http import HttpError
from app.ai.sorting import collections
from app.db.items_repo import NewItem, save_transcript, upsert_item
from app.services import AppServices
from tests.fakes import FakeNet
from tests.test_jobs import wait_for_status

OLLAMA = "http://localhost:11434"
NAMES = ["Cooking", "Want to go", "Music", "Gym"]
# The AI files and tags by itself only when the user switches these on.
AUTO = {"auto_sort": True, "auto_tag": True}


def as_fit(score: float) -> str:
    return "clear" if score >= 0.9 else "likely" if score >= 0.7 else "maybe" if score >= 0.45 else "guess"


def notes(collections_: list[tuple[str, float]], **extra: Any) -> dict[str, Any]:
    return {
        "title": extra.get("title", "A video"),
        "summary": extra.get("summary", "What it's about."),
        "kind": extra.get("kind", "other"),
        "facts": ["one fact"],
        "steps": ["do this", "then that"],
        "tags": ["Tag", "#tag", "other"],
        "collections": [{"name": name, "fit": as_fit(conf)} for name, conf in collections_],
    }


def fake_ai(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Answers like a model would, based on a word in the video's caption."""
    assert payload is not None
    text = next(m["content"] for m in payload["messages"] if "Caption:" in m["content"])
    caption = re.search(r"Caption: (.*)", text)
    word = caption.group(1) if caption else ""
    if "broken" in word:
        return {"message": {"content": "sorry, no JSON today"}}
    if "pasta" in word:
        answer = notes([("Cooking", 0.95)], title="Carbonara", kind="recipe")
    elif "london" in word:
        answer = notes([("Want to go", 0.9), ("Music", 0.3)], kind="travel")
    elif "squat" in word:
        answer = notes([("Gym", 0.97)], kind="workout")
    elif "blank" in word:  # what a model says when its prompt was cut short
        answer = notes([("Music", 0.4)], title="No video provided",
                       summary="Please provide a video, transcript, or caption to generate a summary.")
    else:
        answer = notes([("Music", 0.4), ("Car stuff", 0.9)])
    if '{"tags"' in text:  # the AI tags question
        answer = {"tags": ["Fresh", "#fresh", "dinner", "x" * 50]}
    elif "Notes already written" in text:  # the re-sort question has no notes fields
        answer = {"collections": answer["collections"]}
    return {"message": {"content": json.dumps(answer)}}


@pytest.fixture
def ollama(net: FakeNet) -> FakeNet:
    net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": "gemma4:12b"}]})
    net.on("POST", f"{OLLAMA}/api/chat", fake_ai)
    return net


def seed(svc: AppServices, *captions: str, status: str = "enriched") -> list[int]:
    ids = []
    with svc.db.connect() as conn:
        for name in NAMES:
            collections.ensure(conn, name)
        for number, caption in enumerate(captions):
            item_id, _ = upsert_item(conn, NewItem(platform="tiktok", url=f"https://t/{number}",
                                                   saved_at=f"2024-01-{number + 1:02d}T00:00:00Z"))
            conn.execute("UPDATE items SET status = ?, description = ?, author = 'someone' WHERE id = ?",
                         (status, caption, item_id))
            save_transcript(conn, item_id, f"transcript about {caption}", "en", "whisper-small")
            ids.append(item_id)
    svc.settings.set(collections.SEEDED_KEY, True)
    return ids


def run_job(svc: AppServices, kind: str, ids: list[int], **params: Any) -> dict[str, Any]:
    svc.runner.start()
    job_id = svc.runner.submit(kind, "AI", {"item_ids": ids, **params})
    return wait_for_status(svc, job_id, "done", "failed")


def row(svc: AppServices, item_id: int) -> dict[str, Any]:
    with svc.db.connect() as conn:
        item = dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
        result = conn.execute("SELECT * FROM ai_results WHERE item_id = ?", (item_id,)).fetchone()
        item["ai"] = dict(result) if result else None
        item["links"] = {link["name"]: link["source"] for link in collections.links_of(conn, item_id)}
    return item


def test_notes_only_suggest_by_default(svc: AppServices, ollama: FakeNet) -> None:
    pasta, vague = seed(svc, "pasta", "something")
    job = run_job(svc, "notes", [pasta, vague])
    assert job["message"] == "Wrote notes for 2 videos: 2 in Unsorted with a suggestion."
    first = row(svc, pasta)
    assert first["status"] == "processed" and first["safe_to_unsave"] == 1  # notes in: safe to unsave
    assert first["links"] == {}  # not filed: Cooking is only a suggestion
    assert json.loads(first["ai"]["suggestions_json"]) == [{"name": "Cooking", "confidence": 0.95}]
    assert json.loads(first["ai"]["tag_suggestions_json"]) == ["tag", "other"]
    with svc.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM item_tags").fetchone()[0] == 0  # no tags put on
    # A name that isn't one of the user's collections is never suggested.
    assert json.loads(row(svc, vague)["ai"]["suggestions_json"]) == [{"name": "Music", "confidence": 0.25}]


def test_notes_that_say_nothing_are_never_kept(svc: AppServices, ollama: FakeNet) -> None:
    (blank,) = seed(svc, "blank")
    job = run_job(svc, "notes", [blank])
    assert job["message"] == "Wrote notes for 0 videos: 1 failed."
    item = row(svc, blank)
    assert item["status"] == "enriched" and item["ai"] is None and item["safe_to_unsave"] == 0
    assert item["error"].startswith("The AI's notes for this one didn't make sense")
    assert len([r for r in ollama.requests if r["url"].endswith("/api/chat")]) == 2  # asked once more first


def test_notes_and_resort_preserve_import_placements(svc: AppServices, ollama: FakeNet) -> None:
    (pasta,) = seed(svc, "pasta")
    with svc.db.connect() as conn:
        inbox = collections.ensure(conn, "TikTok Inbox")
        collections.add_from_platform(conn, pasta, inbox)
    assert run_job(svc, "notes", [pasta])["status"] == "done"
    assert row(svc, pasta)["links"] == {"TikTok Inbox": "platform"}
    assert run_job(svc, "sort", [pasta], keep_manual=False)["status"] == "done"
    assert row(svc, pasta)["links"] == {"TikTok Inbox": "platform"}


def test_notes_are_written_and_videos_sorted(svc: AppServices, ollama: FakeNet) -> None:
    svc.settings.set("sorting", AUTO)
    pasta, london, vague, broken = seed(svc, "pasta", "london", "something", "broken")
    job = run_job(svc, "notes", [pasta, london, vague, broken])
    assert job["status"] == "done", job
    assert job["message"] == "Wrote notes for 3 videos: 2 sorted, 1 in Unsorted with a suggestion, 1 failed."
    assert job["result"]["ai"] == "Ollama · gemma4:12b"

    first = row(svc, pasta)
    assert first["status"] == "processed" and first["processed_at"] and first["safe_to_unsave"] == 1
    assert first["links"] == {"Cooking": "ai"}
    ai = first["ai"]
    assert (ai["title"], ai["kind"], ai["category"], ai["confidence"]) == ("Carbonara", "recipe", "Cooking", 0.95)
    assert json.loads(ai["steps_json"]) == [{"text": "do this", "done": False}, {"text": "then that", "done": False}]
    assert json.loads(ai["tags"]) == ["tag", "other"]
    assert ai["provider"] == "Ollama" and ai["model"] == "gemma4:12b"

    assert row(svc, london)["links"] == {"Want to go": "ai"}  # Music at 30% isn't added
    unsure = row(svc, vague)
    assert unsure["links"] == {} and unsure["needs_review"] == 0
    assert json.loads(unsure["ai"]["suggestions_json"]) == [{"name": "Music", "confidence": 0.25}]

    failed = row(svc, broken)
    assert failed["status"] == "enriched" and failed["error"].startswith("The AI didn't return usable results")

    # Running it again only does what's left.
    calls = len(ollama.requests)
    again = run_job(svc, "notes", [pasta, london])
    assert again["message"] == "Nothing to do: these videos were already done."
    assert len(ollama.requests) == calls


def test_the_job_stops_when_the_ai_cant_be_reached(svc: AppServices, net: FakeNet) -> None:
    ids = seed(svc, "pasta", "london", "squat")
    net.on("POST", f"{OLLAMA}/api/chat", HttpError("Couldn't connect: refused", status=None))
    job = run_job(svc, "notes", ids)
    assert job["status"] == "failed"
    assert "Couldn't reach Ollama" in job["error"] and "press Resume" in job["error"]
    assert row(svc, ids[2])["status"] == "enriched"  # never tried; Resume does it


def test_rules_win_and_the_users_moves_survive_a_resort(svc: AppServices, ollama: FakeNet) -> None:
    pasta, london = seed(svc, "pasta", "london")
    with svc.db.connect() as conn:
        collections.ensure(conn, "Japan trip")
    svc.settings.set("sorting", {**AUTO, "rules": [{"field": "text", "value": "london", "collection": "Japan trip"},
                                                   {"field": "text", "value": "london", "collection": "Gone"}]})
    run_job(svc, "notes", [pasta, london])
    assert row(svc, london)["links"] == {"Japan trip": "rule", "Want to go": "ai"}

    # The user drags the pasta video into Gym; a re-sort keeps that.
    with svc.db.connect() as conn:
        gym = collections.find(conn, "Gym")["id"]  # type: ignore[index]
        cooking = collections.find(conn, "Cooking")["id"]  # type: ignore[index]
        collections.move(conn, pasta, cooking, gym)
    svc.settings.set("sorting", AUTO)  # rule removed
    job = run_job(svc, "sort", [pasta, london])
    assert job["status"] == "done" and job["message"].startswith("Re-sorted 2 videos")
    assert row(svc, pasta)["links"] == {"Gym": "user"}
    assert row(svc, london)["links"] == {"Want to go": "ai"}

    # Without "keep the ones I placed", the AI's choice comes back.
    run_job(svc, "sort", [pasta], keep_manual=False)
    assert row(svc, pasta)["links"] == {"Cooking": "ai"}


# ---------- routes ----------


def test_collections_routes(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    ids = seed(svc, "pasta", "something")
    run_job(svc, "notes", ids)
    data = api.get("/api/collections").json()
    assert [c["name"] for c in data["collections"]] == NAMES
    assert data["counts"] == {"waiting": 0, "processed": 2, "unsorted": 2, "suggested": 2, "tag_suggested": 2,
                              "untagged": 2, "ai_filed": 0, "ai_tagged": 0}

    made = api.post("/api/collections", json={"name": "Japan trip"}).json()
    assert "Japan trip" in [c["name"] for c in made["collections"]]
    assert api.post("/api/collections", json={"name": "japan TRIP"}).status_code == 400
    trip = made["created_id"]
    assert api.patch(f"/api/collections/{trip}", json={"name": "Japan 2027"}).status_code == 200
    assert api.patch(f"/api/collections/{trip}", json={"name": "Cooking"}).status_code == 400
    assert api.delete(f"/api/collections/{trip}").status_code == 200
    assert api.delete("/api/collections/9999").status_code == 404


def test_unsorted_accepting_suggestions_and_tags(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    pasta, vague = seed(svc, "pasta", "something")
    run_job(svc, "notes", [pasta, vague])
    names = {c["name"]: c["id"] for c in api.get("/api/collections").json()["collections"]}

    unsorted = api.get("/api/library", params={"view": "unsorted"}).json()
    assert [card["id"] for card in unsorted] == [vague, pasta]
    card = unsorted[0]
    assert card["suggestions"] == [{"name": "Music", "confidence": 0.25}]
    assert card["tag_suggestions"] == ["tag", "other"]
    assert card["steps"] == ["do this", "then that"] and card["facts"] == ["one fact"]
    assert "needs_review" not in card and "new_collection" not in card

    # One click: the AI's pick. Or a different one. Or all of them at once.
    assert [l["name"] for l in api.post(f"/api/review/{vague}/accept", json={}).json()["collections"]] == ["Music"]
    api.delete(f"/api/items/{vague}/collections/{names['Music']}")
    chosen = api.post(f"/api/review/{vague}/accept", json={"collection_id": names["Gym"]}).json()
    assert [(l["name"], l["source"]) for l in chosen["collections"]] == [("Gym", "user")]
    assert api.post("/api/review/accept-all").json() == {"accepted": 1}
    assert api.get("/api/library", params={"view": "unsorted"}).json() == []
    cooking = api.get("/api/library", params={"view": "collection", "collection_id": names["Cooking"]}).json()
    assert [c["id"] for c in cooking] == [pasta] and cooking[0]["kind_label"] == "Recipe"
    assert api.get("/api/library", params={"view": "collection"}).status_code == 400

    # Suggested tags: yes to one, no to the other.
    tagged = api.post(f"/api/items/{pasta}/tag-suggestions", json={"names": ["tag"]}).json()
    assert tagged["tags"] == ["tag"] and tagged["tag_suggestions"] == ["other"]
    declined = api.post(f"/api/items/{pasta}/tag-suggestions", json={"names": ["other"], "accept": False}).json()
    assert declined["tags"] == ["tag"] and declined["tag_suggestions"] == []

    # Drag and drop: from Cooking to Gym.
    moved = api.post(f"/api/items/{pasta}/move", json={"from_id": names["Cooking"], "to_id": names["Gym"]}).json()
    assert [(l["name"], l["source"]) for l in moved["collections"]] == [("Gym", "user")]
    assert api.post(f"/api/items/{pasta}/move", json={"to_id": 9999}).status_code == 404
    emptied = api.delete(f"/api/items/{pasta}/collections/{names['Gym']}").json()
    assert emptied["collections"] == []
    assert [c["id"] for c in api.get("/api/library", params={"view": "unsorted"}).json()] == [pasta]


def test_starting_notes_checks_the_ai_first(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    assert api.post("/api/notes/start", json={"count": 5}).status_code == 400  # nothing waiting
    seed(svc, "pasta")
    net.on("GET", f"{OLLAMA}/api/tags", {"models": []})
    missing = api.post("/api/notes/start", json={"count": 5})
    assert missing.status_code == 400 and missing.json()["code"] == "model_missing"

    net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": "gemma4:12b"}]})
    net.on("POST", f"{OLLAMA}/api/chat", fake_ai)
    job = api.post("/api/notes/start", json={"count": 5}).json()
    assert job["title"] == "AI notes for 1 video"
    wait_for_status(svc, job["id"], "done")


def test_cloud_ai_asks_before_spending_money(api: TestClient, svc: AppServices, keys: Any) -> None:
    seed(svc, *[f"video {n}" for n in range(60)])
    api.put("/api/ai/current", json={"provider": "anthropic"})
    keys.set("anthropic", "sk-test-not-real")
    api.put("/api/ai/providers/anthropic", json={"model": "claude-haiku-5-5"})

    asked = api.post("/api/notes/start", json={"count": None})
    assert asked.status_code == 409
    body = asked.json()
    assert body["code"] == "confirm_cost" and body["requests"] == 50  # cloud batches stop at 50
    assert "50 requests" in body["detail"] and "API key pays" in body["detail"]

    job = api.post("/api/notes/start", json={"count": None, "confirm_cost": True}).json()
    assert len(job["params"]["item_ids"]) == 50


def test_resort_route(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    assert api.post("/api/sorting/resort", json={}).status_code == 400
    ids = seed(svc, "pasta", "something")
    run_job(svc, "notes", ids)
    job = api.post("/api/sorting/resort", json={"which": "unsorted"}).json()
    assert job["params"]["item_ids"] == [ids[1], ids[0]] and job["params"]["keep_manual"] is True
    done = wait_for_status(svc, job["id"], "done")
    assert done["message"] == "Re-sorted 2 videos: 2 in Unsorted with a suggestion."
    url = "/api/sorting/resort"
    assert api.post(url, json={"which": "unsorted", "item_ids": []}).status_code == 400
    selected = api.post(url, json={"which": "unsorted", "item_ids": ids[:1]}).json()
    assert selected["params"]["item_ids"] == ids[:1]


def test_sorting_settings_route(api: TestClient, svc: AppServices) -> None:
    data = api.get("/api/sorting/settings").json()
    assert data["settings"]["mode"] == "my_list" and data["settings"]["auto_sort"] is False
    assert "safe_to_unsave" not in data["settings"] and "no_collection_tag" not in data["settings"]
    assert [k["id"] for k in data["kinds"]][:2] == ["recipe", "travel"]
    changed = dict(data["settings"], auto_sort=True, review_below=0.75,
                   rules=[{"field": "author", "value": "@chef", "collection": "Cooking"}])
    saved = api.put("/api/sorting/settings", json=changed).json()["settings"]
    assert saved["auto_sort"] is True and saved["review_below"] == 0.75
    assert saved["rules"][0]["value"] == "@chef"
    bad = dict(changed, max_collections=7)
    assert api.put("/api/sorting/settings", json=bad).status_code == 422


def test_clearing_what_the_ai_did(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import tags

    svc.settings.set("sorting", AUTO)
    pasta, vague = seed(svc, "pasta", "something")
    run_job(svc, "notes", [pasta, vague])
    with svc.db.connect() as conn:
        tags.add(conn, pasta, "mine")
    counts = api.get("/api/notes/overview").json()["counts"]
    assert (counts["ai_filed"], counts["ai_tagged"], counts["suggested"]) == (1, 4, 1)

    assert api.post("/api/sorting/clear", json={"what": "ai_collections"}).json() == {"cleared": 1}
    assert row(svc, pasta)["links"] == {}  # back in Unsorted
    assert api.post("/api/sorting/clear", json={"what": "ai_tags"}).json() == {"cleared": 4}
    with svc.db.connect() as conn:
        assert [t["name"] for t in tags.of_item(conn, pasta)] == ["mine"]  # the user's own stays
    api.post("/api/sorting/clear", json={"what": "suggestions"})
    assert api.get("/api/notes/overview").json()["counts"]["suggested"] == 0
    assert api.post("/api/sorting/clear", json={"what": "everything"}).status_code == 422


def test_tags_folders_and_switched_off_collections(svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import tags
    from app.ai.sorting.settings import Rule, SortingSettings, save

    save(svc.settings, SortingSettings(ai_folder="AI ideas", auto_sort=True, auto_tag=True,
                                       rules=[Rule(field="text", value="pasta", tag="italian")]))
    pasta, vague, squat = seed(svc, "pasta", "something", "squat")
    with svc.db.connect() as conn:
        folder = collections.ensure(conn, "AI ideas")
        collections.update(conn, collections.find(conn, "Gym")["id"], ai_allowed=False)
    seen: list[str] = []
    ollama.on("POST", f"{OLLAMA}/api/chat", lambda payload: (seen.append(payload["messages"][1]["content"]),
                                                            fake_ai(payload))[1])
    assert run_job(svc, "notes", [pasta, vague, squat])["status"] == "done"
    assert "- Gym" not in seen[0] and "- Cooking" in seen[0]  # the AI never sees switched-off ones

    with svc.db.connect() as conn:
        on_pasta = {t["name"]: t["source"] for t in tags.of_item(conn, pasta)}
        assert on_pasta == {"tag": "ai", "other": "ai", "italian": "rule"}
        # Its only pick is a weak one, so it's in no collection, and there's no "unsorted" tag.
        assert "unsorted" not in {t["name"] for t in tags.of_item(conn, vague)}
        # The AI picked "Gym", which is switched off: it mustn't use it.
        assert collections.links_of(conn, squat) == []
        assert collections.find(conn, "AI ideas")["id"] == folder


# ---------- AI tags, AI sort and platform links ----------


def test_ai_tags_reuse_and_keep_the_users_own(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import tags

    svc.settings.set("sorting", {"auto_tag": True})
    pasta, london = seed(svc, "pasta", "london")
    with svc.db.connect() as conn:
        tags.add(conn, pasta, "mine")
    started = api.post("/api/tags/ai", json={"which": "with_notes"})
    assert started.status_code == 200, started.text
    job = wait_for_status(svc, started.json()["id"], "done", "failed")
    assert job["message"] == "Tagged 2 videos."
    with svc.db.connect() as conn:
        on_pasta = {(t["name"], t["source"]) for t in tags.of_item(conn, pasta)}
    assert on_pasta == {("mine", "user"), ("fresh", "ai"), ("dinner", "ai")}  # the over-long one is dropped, repeats merged

    asked = next(r for r in ollama.requests if '{"tags"' in json.dumps(r))
    assert "tags the user already has (write them exactly)" in json.dumps(asked)
    none_left = api.post("/api/tags/ai", json={"which": "untagged"})
    assert none_left.status_code == 400  # every save has tags now


def test_ai_sort_for_picked_saves_only(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    pasta, london = seed(svc, "pasta", "london")
    run_job(svc, "notes", [pasta, london])
    started = api.post("/api/sorting/resort", json={"item_ids": [pasta]}).json()
    job = wait_for_status(svc, started["id"], "done", "failed")
    assert job["message"].startswith("Re-sorted 1 video")


def test_platform_collections_link_to_mine(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        for n, (platform, where) in enumerate([("youtube", "Recipes, Watch later"), ("youtube", "recipes"),
                                               ("youtube", None)]):
            item_id, _ = upsert_item(conn, NewItem(platform=platform, url=f"https://y/{n}",
                                                   platform_collection=where))
            if where == "Recipes, Watch later":
                conn.execute("UPDATE items SET platform_collections_json = ? WHERE id = ?",
                             ('["Recipes", "Watch later"]', item_id))
        conn.execute(
            "INSERT INTO jobs (kind, title, status, result_json) VALUES ('import', 'Import', 'done', ?)",
            ('{"platforms": [{"platform": "tiktok", "collections": ["Gym", "Food ideas"]}]}',),
        )
    links = api.get("/api/platform-collections").json()
    by_name = {(l["platform"], l["name"]): l for l in links["links"]}
    assert by_name[("youtube", "Recipes")]["count"] == 2 and by_name[("youtube", "Recipes")]["membership_known"]
    assert not by_name[("tiktok", "Gym")]["membership_known"]  # TikTok only lists names

    food = next(c["id"] for c in api.get("/api/collections").json()["collections"] if c["name"] == "Food")
    linked = api.put("/api/platform-collections", json={"platform": "youtube", "name": "Recipes",
                                                       "collection_id": food, "mode": "auto"}).json()
    assert linked["filed"] == 2
    entry = next(l for l in linked["links"] if l["name"] == "Recipes")
    assert (entry["collection_name"], entry["mode"], entry["filed"]) == ("Food", "auto", 2)

    manual = api.put("/api/platform-collections", json={"platform": "youtube", "name": "Watch later",
                                                       "create_collection": True, "mode": "manual"}).json()
    assert manual["filed"] == 0  # manual: nothing until "Add now"
    added = api.post("/api/platform-collections/apply", json={"platform": "youtube", "name": "Watch later"}).json()
    assert added["filed"] == 1
    assert "Watch later" in [c["name"] for c in api.get("/api/collections").json()["collections"]]

    gone = api.put("/api/platform-collections", json={"platform": "youtube", "name": "Recipes", "collection_id": None})
    assert next(l for l in gone.json()["links"] if l["name"] == "Recipes")["collection_id"] is None
    assert api.post("/api/platform-collections/apply", json={"platform": "youtube", "name": "Recipes"}).status_code == 400


def test_partial_sort_choices_keep_other_settings(api: TestClient) -> None:
    path = "/api/sorting/settings"
    assert api.patch(path, json={"auto_tag": True, "kind_steps": {"recipe": "Keep the ingredients."}}).status_code == 200
    assert api.patch(path, json={"auto_sort": True, "kind_steps": {"travel": "Keep opening times."}}).status_code == 200
    assert api.patch(path, json={"auto_tag": False, "max_collections": 0}).status_code == 422
    saved = api.get(path).json()["settings"]
    assert saved["auto_sort"] and saved["auto_tag"] and not saved["auto_notes"]
    assert saved["kind_steps"]["recipe"] == "Keep the ingredients."
    assert saved["kind_steps"]["travel"] == "Keep opening times."


def test_queued_local_notes_never_switch_to_cloud(svc: AppServices, ollama: FakeNet) -> None:
    ids = seed(svc, "pasta")
    svc.ai.set_current("anthropic")
    blocked = run_job(svc, "notes", ids)
    assert blocked["status"] == "failed"
    assert "confirm the current cloud model and cost" in blocked["error"]
    assert not ollama.requests
    assert run_job(svc, "notes", ids, provider_id="ollama")["status"] == "done"
    assert all(request["url"].startswith(OLLAMA) for request in ollama.requests)


def test_notes_can_start_by_themselves_when_transcripts_finish(svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting.settings import SortingSettings, load, save
    from types import SimpleNamespace

    from app.services import notes_after

    ctx = SimpleNamespace(cancelled=False)
    seed(svc, "pasta", "london")
    after_transcripts = notes_after(lambda ctx: {"message": "done"}, svc.db, svc.settings, svc.ai, svc.runner, svc.jobs)

    assert load(svc.settings).auto_notes is False
    assert after_transcripts(ctx) == {"message": "done"}  # type: ignore[arg-type]
    assert [job["kind"] for job in svc.jobs.recent()] == []  # off unless the user switches it on

    save(svc.settings, SortingSettings(auto_notes=True))
    ctx.cancelled = True
    after_transcripts(ctx)  # type: ignore[arg-type]
    assert not svc.jobs.recent()
    ctx.cancelled = False
    after_transcripts(ctx)  # type: ignore[arg-type]
    started = [job for job in svc.jobs.recent() if job["kind"] == "notes"]
    assert len(started) == 1 and started[0]["title"] == "AI notes for 2 videos"
    after_transcripts(ctx)  # type: ignore[arg-type]
    assert len([job for job in svc.jobs.recent() if job["kind"] == "notes"]) == 1  # never two at once
