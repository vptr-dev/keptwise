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


def as_fit(score: float) -> str:
    return "clear" if score >= 0.9 else "likely" if score >= 0.7 else "maybe" if score >= 0.45 else "guess"


def notes(collections_: list[tuple[str, float]], idea: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "title": extra.get("title", "A video"),
        "summary": "What it's about.",
        "kind": extra.get("kind", "other"),
        "facts": ["one fact"],
        "steps": ["do this", "then that"],
        "tags": ["Tag", "#tag", "other"],
        "collections": [{"name": name, "fit": as_fit(conf)} for name, conf in collections_],
        "new_collection": idea,
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
    else:
        answer = notes([("Music", 0.4)], idea="Car stuff")
    if '{"tags"' in text:  # the AI tags question
        answer = {"tags": ["Fresh", "#fresh", "dinner", "x" * 50]}
    elif "Notes already written" in text:  # the re-sort question has no notes fields
        answer = {"collections": answer["collections"], "new_collection": answer["new_collection"]}
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


def test_notes_are_written_and_videos_sorted(svc: AppServices, ollama: FakeNet) -> None:
    pasta, london, vague, broken = seed(svc, "pasta", "london", "something", "broken")
    job = run_job(svc, "notes", [pasta, london, vague, broken])
    assert job["status"] == "done", job
    assert job["message"] == "Wrote notes for 3 videos: 2 sorted, 1 waiting in Needs review, 1 failed."
    assert job["result"]["ai"] == "Ollama · gemma4:12b"

    first = row(svc, pasta)
    assert first["status"] == "processed" and first["processed_at"] and first["safe_to_unsave"] == 1
    assert first["links"] == {"Cooking": "ai"} and first["needs_review"] == 0
    ai = first["ai"]
    assert (ai["title"], ai["kind"], ai["category"], ai["confidence"]) == ("Carbonara", "recipe", "Cooking", 0.95)
    assert json.loads(ai["steps_json"]) == [{"text": "do this", "done": False}, {"text": "then that", "done": False}]
    assert json.loads(ai["tags"]) == ["tag", "other"]
    assert ai["provider"] == "Ollama" and ai["model"] == "gemma4:12b"

    assert row(svc, london)["links"] == {"Want to go": "ai"}  # Music at 30% isn't added
    unsure = row(svc, vague)
    assert unsure["needs_review"] == 1 and unsure["links"] == {}
    assert unsure["review_reason"].startswith("The AI suggests a new collection: “Car stuff”.")
    assert unsure["ai"]["new_collection"] == "Car stuff"

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
    svc.settings.set("sorting", {"rules": [{"field": "text", "value": "london", "collection": "Japan trip"},
                                           {"field": "text", "value": "london", "collection": "Gone"}]})
    run_job(svc, "notes", [pasta, london])
    assert row(svc, london)["links"] == {"Japan trip": "rule", "Want to go": "ai"}

    # The user drags the pasta video into Gym; a re-sort keeps that.
    with svc.db.connect() as conn:
        gym = collections.find(conn, "Gym")["id"]  # type: ignore[index]
        cooking = collections.find(conn, "Cooking")["id"]  # type: ignore[index]
        collections.move(conn, pasta, cooking, gym)
    svc.settings.set("sorting", {})  # rule removed
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
    assert data["counts"] == {"waiting": 0, "processed": 2, "review": 1, "unsorted": 0, "untagged": 0}

    made = api.post("/api/collections", json={"name": "Japan trip"}).json()
    assert "Japan trip" in [c["name"] for c in made["collections"]]
    assert api.post("/api/collections", json={"name": "japan TRIP"}).status_code == 400
    trip = made["created_id"]
    assert api.patch(f"/api/collections/{trip}", json={"name": "Japan 2027"}).status_code == 200
    assert api.patch(f"/api/collections/{trip}", json={"name": "Cooking"}).status_code == 400
    assert api.delete(f"/api/collections/{trip}").status_code == 200
    assert api.delete("/api/collections/9999").status_code == 404


def test_library_views_move_and_review(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    pasta, vague = seed(svc, "pasta", "something")
    run_job(svc, "notes", [pasta, vague])
    names = {c["name"]: c["id"] for c in api.get("/api/collections").json()["collections"]}

    review = api.get("/api/library", params={"view": "review"}).json()
    assert [card["id"] for card in review] == [vague]
    card = review[0]
    assert card["needs_review"] and card["new_collection"] == "Car stuff"
    assert card["suggestions"] == [{"name": "Music", "confidence": 0.25}]
    assert card["steps"] == ["do this", "then that"] and card["facts"] == ["one fact"]

    cooking = api.get("/api/library", params={"view": "collection", "collection_id": names["Cooking"]}).json()
    assert [c["id"] for c in cooking] == [pasta] and cooking[0]["kind_label"] == "Recipe"
    assert api.get("/api/library", params={"view": "collection"}).status_code == 400

    # Approving the AI's idea makes the new collection and files the video.
    accepted = api.post(f"/api/review/{vague}/accept", json={}).json()
    assert [l["name"] for l in accepted["collections"]] == ["Car stuff"]
    assert accepted["needs_review"] is False
    assert api.get("/api/library", params={"view": "review"}).json() == []

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
    job = api.post("/api/sorting/resort", json={"which": "review"}).json()
    assert job["params"]["item_ids"] == [ids[1]] and job["params"]["keep_manual"] is True
    done = wait_for_status(svc, job["id"], "done")
    assert done["message"] == "Re-sorted 1 video: 1 waiting in Needs review."


def test_sorting_settings_route(api: TestClient, svc: AppServices) -> None:
    data = api.get("/api/sorting/settings").json()
    assert data["settings"]["mode"] == "my_list_plus_ideas"
    assert [k["id"] for k in data["kinds"]][:2] == ["recipe", "travel"]
    changed = dict(data["settings"], mode="my_list", review_below=0.75,
                   rules=[{"field": "author", "value": "@chef", "collection": "Cooking"}])
    saved = api.put("/api/sorting/settings", json=changed).json()["settings"]
    assert saved["mode"] == "my_list" and saved["review_below"] == 0.75
    assert saved["rules"][0]["value"] == "@chef"
    bad = dict(changed, max_collections=7)
    assert api.put("/api/sorting/settings", json=bad).status_code == 422


def test_safe_to_unsave_follows_the_setting(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    (item_id,) = seed(svc, "pasta")
    run_job(svc, "notes", [item_id])
    assert row(svc, item_id)["safe_to_unsave"] == 1
    settings = api.get("/api/sorting/settings").json()["settings"]
    api.put("/api/sorting/settings", json=dict(settings, safe_to_unsave="done"))
    assert row(svc, item_id)["safe_to_unsave"] == 0  # not ticked done yet


def test_tags_folders_and_switched_off_collections(svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import tags
    from app.ai.sorting.settings import Rule, SortingSettings, save

    save(svc.settings, SortingSettings(ai_folder="AI ideas", no_collection_tag="unsorted", mode="ai_decides",
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
        # Its only pick is a weak one, so it's in no collection and gets the tag.
        assert "unsorted" in {t["name"] for t in tags.of_item(conn, vague)}
        # The AI picked "Gym", which is switched off: even "AI decides" mustn't use it.
        assert collections.links_of(conn, squat) == []
        assert collections.find(conn, "AI ideas")["id"] == folder


# ---------- AI tags, AI sort and platform links ----------


def test_ai_tags_reuse_and_keep_the_users_own(api: TestClient, svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import tags

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


def test_notes_can_start_by_themselves_when_transcripts_finish(svc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting.settings import SortingSettings, load, save
    from app.services import notes_after

    seed(svc, "pasta", "london")
    after_transcripts = notes_after(lambda ctx: {"message": "done"}, svc.db, svc.settings, svc.ai, svc.runner, svc.jobs)

    assert load(svc.settings).auto_notes is False
    assert after_transcripts(None) == {"message": "done"}  # type: ignore[arg-type]
    assert [job["kind"] for job in svc.jobs.recent()] == []  # off unless the user switches it on

    save(svc.settings, SortingSettings(auto_notes=True))
    after_transcripts(None)  # type: ignore[arg-type]
    started = [job for job in svc.jobs.recent() if job["kind"] == "notes"]
    assert len(started) == 1 and started[0]["title"] == "AI notes for 2 videos"
    after_transcripts(None)  # type: ignore[arg-type]
    assert len([job for job in svc.jobs.recent() if job["kind"] == "notes"]) == 1  # never two at once
