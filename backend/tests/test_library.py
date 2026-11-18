"""Tests for the Library grid, checklists, Plans, the Safe to unsave list and the theme setting."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.sorting.settings import SortingSettings, save
from app.db.items_repo import NewItem, update_item, upsert_item
from app.library import unsave_export
from app.services import AppServices


def add(svc: AppServices, n: int, *, processed: bool = True, kind: str = "recipe", platform: str = "tiktok",
        saved_at: str = "2026-01-01", steps: int = 3) -> int:
    with svc.db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem(platform, f"https://example.com/{platform}/{n}", saved_at=saved_at))
        if processed:
            update_item(conn, item_id, status="processed", safe_to_unsave=1)
            conn.execute(
                "INSERT INTO ai_results (item_id, title, summary, kind, steps_json) VALUES (?, ?, ?, ?, ?)",
                (item_id, f"Video {n}", "Short summary", kind,
                 json.dumps([{"text": f"Step {s}", "done": False} for s in range(steps)])),
            )
    return item_id


def test_library_filters_sorts_and_pages(api: TestClient, svc: AppServices) -> None:
    add(svc, 1, saved_at="2026-01-01")
    add(svc, 2, saved_at="2026-03-01", kind="travel")
    add(svc, 3, processed=False, saved_at="2026-02-01")
    add(svc, 4, platform="youtube", saved_at="2026-04-01")

    everything = api.get("/api/library/items").json()
    assert everything["total"] == 4
    assert [i["title"] for i in everything["items"]] == ["Video 4", "Video 2", None, "Video 1"]

    assert api.get("/api/library/items?status=waiting").json()["total"] == 1
    assert [i["title"] for i in api.get("/api/library/items?kind=travel").json()["items"]] == ["Video 2"]
    assert api.get("/api/library/items?platform=youtube").json()["total"] == 1
    oldest = api.get("/api/library/items?sort=oldest&limit=2&offset=1").json()
    assert oldest["total"] == 4 and [i["title"] for i in oldest["items"]] == [None, "Video 2"]
    by_title = api.get("/api/library/items?sort=title").json()["items"]
    assert by_title[-1]["title"] is None  # untitled ones go last

    filters = api.get("/api/library/filters").json()
    assert {p["id"]: p["count"] for p in filters["platforms"]} == {"tiktok": 3, "youtube": 1}
    assert {k["id"]: k["count"] for k in filters["kinds"]}["recipe"] == 2


def test_ticking_steps_and_done(api: TestClient, svc: AppServices) -> None:
    item_id = add(svc, 1)
    card = api.put(f"/api/items/{item_id}/steps/1", json={"done": True}).json()
    assert card["steps_checked"] == [False, True, False]
    assert card["started_at"]
    assert api.put(f"/api/items/{item_id}/steps/9", json={"done": True}).status_code == 404
    assert api.get("/api/library/items?progress=started").json()["total"] == 1
    assert api.patch(f"/api/items/{item_id}", json={"done": True}).json()["done"] is True
    card = api.post(f"/api/items/{item_id}/restart").json()
    assert card["steps_checked"] == [False, False, False] and not card["done"] and not card["started_at"]


def test_plans_hold_one_save_or_many_and_tick_off(api: TestClient, svc: AppServices) -> None:
    first, second, third = add(svc, 1), add(svc, 2), add(svc, 3)
    assert api.get("/api/plans").json() == {"plans": [], "open": 0, "finished": 0}

    solo = api.post("/api/plans", json={"name": "Just this one", "item_ids": [first]}).json()
    assert solo["item_count"] == 1 and solo["items"][0]["item"]["id"] == first
    assert solo["items"][0]["item"]["plans"] == [{"id": solo["id"], "name": "Just this one", "done": False}]

    trip = api.post("/api/plans", json={"name": "Weekend", "note": "Saturday", "item_ids": [second, third]}).json()
    trip = api.post(f"/api/plans/{trip['id']}/items", json={"item_ids": [first, second]}).json()
    assert trip["added"] == 1 and [e["item"]["id"] for e in trip["items"]] == [second, third, first]
    trip = api.post(f"/api/plans/{trip['id']}/order", json={"item_ids": [first]}).json()
    assert [e["item"]["id"] for e in trip["items"]] == [first, second, third]
    assert trip["steps_total"] == 9  # the steps of all three saves

    for item_id in (first, second):
        trip = api.put(f"/api/plans/{trip['id']}/items/{item_id}", json={"done": True}).json()
    assert trip["items_done"] == 2 and not trip["done"]
    trip = api.put(f"/api/plans/{trip['id']}/items/{third}", json={"done": True}).json()
    assert trip["done"]  # every save ticked: the plan is finished
    assert api.get("/api/plans").json()["finished"] == 1
    trip = api.put(f"/api/plans/{trip['id']}/items/{third}", json={"done": False}).json()
    assert not trip["done"]
    assert api.put(f"/api/plans/{trip['id']}/items/99999", json={"done": True}).status_code == 404

    trip = api.delete(f"/api/plans/{trip['id']}/items/{third}").json()
    assert trip["item_count"] == 2
    renamed = api.patch(f"/api/plans/{trip['id']}", json={"name": "Lisbon", "done": True}).json()
    assert renamed["name"] == "Lisbon" and renamed["done"]
    bulk = api.post("/api/items/bulk", json={"item_ids": [third], "action": "add_to_plan", "plan_id": solo["id"]})
    assert bulk.status_code == 200
    assert api.get(f"/api/plans/{solo['id']}").json()["item_count"] == 2
    left = api.delete(f"/api/plans/{solo['id']}").json()
    assert [p["name"] for p in left["plans"]] == ["Lisbon"]
    assert api.get(f"/api/plans/{solo['id']}").status_code == 404
    assert api.get("/api/overview").json()["counts"]["open_plans"] == 0


def test_done_has_nothing_to_do_with_unsaving(api: TestClient, svc: AppServices) -> None:
    item_id = add(svc, 1)
    assert api.patch(f"/api/items/{item_id}", json={"done": True}).json()["safe_to_unsave"] is True
    assert api.patch(f"/api/items/{item_id}", json={"done": False}).json()["safe_to_unsave"] is True


def test_unsave_list_and_marking_unsaved(api: TestClient, svc: AppServices) -> None:
    first = add(svc, 1)
    add(svc, 2)
    add(svc, 3, processed=False)  # not safe yet
    listing = api.get("/api/unsave").json()
    assert listing["left"] == 2 and len(listing["items"]) == 2 and "rule" not in listing

    assert api.patch(f"/api/items/{first}", json={"unsaved": True}).json()["unsaved"] is True
    listing = api.get("/api/unsave").json()
    assert listing["left"] == 1
    assert listing["items"][-1]["id"] == first  # unsaved ones move to the end

    overview = api.get("/api/overview").json()
    assert overview["counts"]["to_unsave"] == 1 and overview["counts"]["unsaved"] == 1
    assert overview["counts"]["total"] == 3 and len(overview["recent"]) == 2


def test_csv_route_has_every_safe_item(api: TestClient, svc: AppServices) -> None:
    add(svc, 1)
    response = api.get("/api/unsave/export.csv")
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == unsave_export.COLUMNS
    assert rows[1][:3] == ["TikTok", "https://example.com/tiktok/1", "Video 1"]


def test_csv_cells_cannot_become_formulas() -> None:
    text = unsave_export.to_csv([{"platform_name": "TikTok", "url": "u", "title": "=HYPERLINK(1)",
                                  "author": "@me", "saved_at": "2026-05-06T10:00:00Z", "collections": [],
                                  "unsaved": True}])
    row = list(csv.reader(io.StringIO(text)))[1]
    assert row[2] == "'=HYPERLINK(1)" and row[3] == "'@me" and row[4] == "2026-05-06" and row[6] == "yes"


def test_saved_csv_never_overwrites(tmp_path: Path) -> None:
    day = date(2026, 11, 11)
    first = unsave_export.save_csv("a", tmp_path, day)
    second = unsave_export.save_csv("b", tmp_path, day)
    assert first.name == "saves-to-unsave-2026-11-11.csv"
    assert second.name == "saves-to-unsave-2026-11-11 (2).csv"
    assert first.read_text(encoding="utf-8-sig") == "a"


def test_export_route_writes_to_downloads(api: TestClient, svc: AppServices, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    assert api.post("/api/unsave/export").status_code == 400  # nothing yet
    add(svc, 1)
    monkeypatch.setattr(unsave_export, "downloads_folder", lambda: tmp_path)
    result = api.post("/api/unsave/export").json()
    assert result["count"] == 1 and Path(result["path"]).parent == tmp_path


def test_look_settings(api: TestClient) -> None:
    first = api.get("/api/ui").json()
    assert first["theme"] == "system" and first["accent"] == "default" and first["start_page"] == "library"
    assert first["dismissed_tips"] == [] and first["card_actions"] is True
    chosen = {**first, "theme": "dark", "accent": "teal", "text_size": "large", "name": "Sam", "compact_sidebar": True}
    assert api.put("/api/ui", json=chosen).json() == chosen
    assert api.get("/api/ui").json() == chosen
    assert api.put("/api/ui", json={"theme": "pink"}).status_code == 422
    assert api.put("/api/ui", json={"accent": "plaid"}).status_code == 422
    # Older saved settings (only a theme) still load, with the rest at their defaults.
    assert api.put("/api/ui", json={"theme": "light"}).json()["accent"] == "default"
    # Home is gone: a saved "home" start page opens the Library.
    assert api.put("/api/ui", json={"start_page": "home"}).json()["start_page"] == "library"


def test_the_platform_picker_narrows_every_list(api: TestClient, svc: AppServices) -> None:
    tiktok = add(svc, 1)
    with svc.db.connect() as conn:
        youtube, _ = upsert_item(conn, NewItem("youtube", "https://youtube.com/watch?v=x", saved_at="2026-05-01"))
    picker = api.get("/api/scope").json()
    assert picker["platform"] is None and {p["id"]: p["count"] for p in picker["platforms"]} == {"tiktok": 1, "youtube": 1}
    assert api.put("/api/scope", json={"platform": "myspace"}).status_code == 400

    assert api.put("/api/scope", json={"platform": "youtube"}).json()["platform"] == "youtube"
    assert [i["id"] for i in api.get("/api/library/items").json()["items"]] == [youtube]
    assert api.get("/api/overview").json()["counts"]["total"] == 1
    assert {p["id"] for p in api.get("/api/library/filters").json()["platforms"]} == {"youtube"}
    assert api.get("/api/library/items?platform=tiktok").json()["items"][0]["id"] == tiktok  # asked for directly

    api.put("/api/scope", json={"platform": None})
    assert api.get("/api/overview").json()["counts"]["total"] == 2


def test_open_item_in_browser(api: TestClient, svc: AppServices, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import library

    opened: list[str] = []
    monkeypatch.setattr(library, "open_in_browser", lambda url: opened.append(url) or True)
    add(svc, 1)
    with svc.db.connect() as conn:
        item_id, url = conn.execute("SELECT id, url FROM items").fetchone()
    assert api.post(f"/api/items/{item_id}/open").json() == {"opened": True}
    assert opened == [url]
    assert api.post("/api/items/9999/open").status_code == 404


def test_plans_in_depth_days_sections_notes_and_todos(api: TestClient, svc: AppServices) -> None:
    from app.ai.sorting import collections

    one, two, three = add(svc, 1), add(svc, 2), add(svc, 3)
    with svc.db.connect() as conn:
        trip = collections.create(conn, "Lisbon")
        food = collections.create(conn, "Lisbon food", parent_id=trip)
        collections.add_by_user(conn, one, trip)
        collections.add_by_user(conn, two, food)

    # Start a plan from a collection: it takes what's inside it too.
    plan = api.post("/api/plans", json={"name": "Weekend in Lisbon", "collection_id": trip, "due_on": "2026-12-24"}).json()
    pid = plan["id"]
    assert sorted(e["item"]["id"] for e in plan["items"]) == [one, two] and plan["due_on"] == "2026-12-24"
    assert api.patch(f"/api/plans/{pid}", json={"due_on": "next week"}).status_code == 400

    # Sections and a note on a save.
    api.patch(f"/api/plans/{pid}/items/{one}", json={"section": "Day 1", "note": "Book ahead"})
    with_todo = api.post(f"/api/plans/{pid}/tasks", json={"text": "Book the hotel", "section": "Before we go"}).json()
    entry = next(e for e in with_todo["items"] if e["item"]["id"] == one)
    assert (entry["section"], entry["note"]) == ("Day 1", "Book ahead")
    assert with_todo["sections"] == ["Day 1", "Before we go"] and with_todo["tasks_total"] == 1
    task = with_todo["tasks"][0]
    assert (task["text"], task["section"], task["done"]) == ("Book the hotel", "Before we go", False)
    renamed = api.post(f"/api/plans/{pid}/sections", json={"old": "Day 1", "new": "Saturday"}).json()
    assert renamed["sections"] == ["Saturday", "Before we go"]

    # Finished only when the saves AND the to-dos are ticked.
    api.put(f"/api/plans/{pid}/items/{one}", json={"done": True})
    almost = api.put(f"/api/plans/{pid}/items/{two}", json={"done": True}).json()
    assert almost["done"] is False
    done = api.patch(f"/api/plans/{pid}/tasks/{task['id']}", json={"done": True}).json()
    assert done["done"] is True and done["tasks_done"] == 1
    again = api.post(f"/api/plans/{pid}/tasks", json={"text": "Pack"}).json()  # a new to-do reopens it
    assert again["done"] is False
    gone = api.delete(f"/api/plans/{pid}/tasks/{again['tasks'][1]['id']}").json()
    assert len(gone["tasks"]) == 1

    # A copy starts fresh: same saves, sections, notes and to-dos, nothing ticked.
    copy = api.post(f"/api/plans/{pid}/copy").json()
    assert copy["name"] == "Weekend in Lisbon (copy)" and copy["items_done"] == 0 and copy["tasks_done"] == 0
    assert next(e for e in copy["items"] if e["item"]["id"] == one)["note"] == "Book ahead"

    # Pinned plans come first, then the soonest day.
    later = api.post("/api/plans", json={"name": "Someday", "item_ids": [three]}).json()
    api.patch(f"/api/plans/{later['id']}", json={"pinned": True})
    order = [p["name"] for p in api.get("/api/plans").json()["plans"] if not p["done"]]
    assert order[0] == "Someday" and order[1] == "Weekend in Lisbon"
    cleared = api.patch(f"/api/plans/{pid}", json={"due_on": None}).json()
    assert cleared["due_on"] is None


def test_a_look_saved_before_the_default_accent_moves_to_it_once(api: TestClient, svc: AppServices) -> None:
    svc.settings.set("ui", {"theme": "dark", "accent": "violet", "name": "Sam"})
    look = api.get("/api/ui").json()
    assert look["accent"] == "default" and look["theme"] == "dark" and look["name"] == "Sam"
    # A colour picked afterwards stays.
    api.put("/api/ui", json=look | {"accent": "teal"})
    assert api.get("/api/ui").json()["accent"] == "teal"
