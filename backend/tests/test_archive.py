"""Deleting saves: the Archive, putting them back, and deleting for good."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.sorting import collections, tags
from app.db.items_repo import NewItem, update_item, upsert_item
from app.services import AppServices
from tests.test_imports_api import SAMPLES, run_import, zip_folder


def add(svc: AppServices, n: int) -> int:
    with svc.db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("tiktok", f"https://example.com/v/{n}", caption=f"Video {n}"))
        update_item(conn, item_id, status="processed")
        conn.execute("INSERT INTO ai_results (item_id, title) VALUES (?, ?)", (item_id, f"Video {n}"))
    return item_id


def library_ids(api: TestClient, extra: str = "") -> list[int]:
    return [item["id"] for item in api.get(f"/api/library/items?sort=oldest{extra}").json()["items"]]


def test_a_deleted_save_moves_to_the_archive_and_comes_back(api: TestClient, svc: AppServices) -> None:
    one, two = add(svc, 1), add(svc, 2)
    with svc.db.connect() as conn:
        food = collections.ensure(conn, "Meals")
        collections.add_by_user(conn, one, food)
        tags.add(conn, one, "pasta")

    card = api.patch(f"/api/items/{one}", json={"deleted": True}).json()
    assert card["deleted"] is True and card["deleted_at"]
    assert library_ids(api) == [two]
    assert library_ids(api, "&archive=deleted") == [one]
    assert api.get("/api/archive").json() == {"deleted": 1, "unsaved": 0, "gone": 0}
    assert card["safe_to_unsave"] is True
    assert card["unsaved"] is False and card["unsaved_at"] is None
    checklist = api.get("/api/unsave").json()
    assert checklist["left"] == 1 and [item["id"] for item in checklist["items"]] == [one]
    # It no longer counts anywhere: collections, tags, the platform picker, the sidebar.
    listed = {c["name"]: c["count"] for c in api.get("/api/collections").json()["collections"]}
    assert listed["Meals"] == 0
    assert {t["name"]: t["count"] for t in api.get("/api/tags").json()["tags"]}["pasta"] == 0
    assert api.get("/api/scope").json()["total"] == 1
    assert api.get(f"/api/library/items?collection_id={food}").json()["total"] == 0
    assert [r["item"]["id"] for r in api.get("/api/search?q=video").json()["results"]] == [two]

    back = api.patch(f"/api/items/{one}", json={"deleted": False}).json()
    assert back["deleted"] is False and [c["name"] for c in back["collections"]] == ["Meals"] and back["tags"] == ["pasta"]
    assert library_ids(api) == [one, two] and library_ids(api, "&archive=deleted") == []
    assert back["safe_to_unsave"] is False
    assert api.get("/api/unsave").json()["items"] == []


def test_unsaved_saves_are_listed_in_the_archive_and_stay_in_the_library(api: TestClient, svc: AppServices) -> None:
    one, two = add(svc, 1), add(svc, 2)
    card = api.patch(f"/api/items/{two}", json={"unsaved": True}).json()
    assert card["unsaved"] is True and card["unsaved_at"]
    assert library_ids(api, "&archive=unsaved") == [two]
    assert library_ids(api) == [one, two]  # the notes are still useful: it stays
    assert api.get("/api/archive").json() == {"deleted": 0, "unsaved": 1, "gone": 0}
    api.post("/api/items/bulk", json={"item_ids": [two], "action": "still_saved"})
    assert library_ids(api, "&archive=unsaved") == []


def test_deleting_for_good_needs_the_archive_first_and_removes_its_files(api: TestClient, svc: AppServices) -> None:
    one = add(svc, 1)
    picture = svc.paths.thumbnails / "1.jpg"
    picture.write_bytes(b"jpg")
    sound = svc.paths.audio / f"{one}.m4a"
    sound.write_bytes(b"sound")
    with svc.db.connect() as conn:
        update_item(conn, one, thumbnail_path="1.jpg")

    assert api.delete(f"/api/items/{one}").status_code == 400  # not from the Library in one step
    api.patch(f"/api/items/{one}", json={"deleted": True})
    assert api.delete(f"/api/items/{one}").json() == {"purged": 1}
    assert not picture.exists() and not sound.exists()
    assert api.get(f"/api/items/{one}").status_code == 404
    with svc.db.connect() as conn:
        assert conn.execute("SELECT url FROM removed_links").fetchone()["url"] == "https://example.com/v/1"
        assert conn.execute("SELECT COUNT(*) FROM ai_results").fetchone()[0] == 0


def test_many_at_once_delete_put_back_delete_for_good(api: TestClient, svc: AppServices) -> None:
    ids = [add(svc, n) for n in range(1, 5)]
    gone = api.post("/api/items/bulk", json={"item_ids": ids[:3], "action": "delete"}).json()
    assert gone["changed"] == 3 and all(card["deleted"] for card in gone["items"])
    assert library_ids(api) == [ids[3]]
    api.post("/api/items/bulk", json={"item_ids": [ids[0]], "action": "restore"})
    # "Delete for good" leaves alone anything that isn't in the Archive.
    purged = api.post("/api/items/bulk", json={"item_ids": [ids[0], ids[1], ids[2]], "action": "purge"}).json()
    assert [card["id"] for card in purged["items"]] == [ids[0]]
    assert library_ids(api) == [ids[0], ids[3]] and library_ids(api, "&archive=deleted") == []


def test_an_import_never_brings_back_what_was_deleted_for_good(api: TestClient, svc: AppServices, tmp_path: Path) -> None:
    archive = zip_folder(SAMPLES / "tiktok_json", tmp_path / "tiktok.zip").read_bytes()
    assert run_import(api, svc, {"tiktok.zip": archive})["result"]["new"] == 3
    first = library_ids(api)[0]
    api.patch(f"/api/items/{first}", json={"deleted": True})
    again = run_import(api, svc, {"tiktok.zip": archive})  # deleted, not for good: still there, still deleted
    assert again["result"]["new"] == 0 and library_ids(api, "&archive=deleted") == [first]

    api.delete(f"/api/items/{first}")
    after = run_import(api, svc, {"tiktok.zip": archive})
    assert after["result"]["new"] == 0 and after["result"]["platforms"][0]["deleted_before"] == 1
    assert after["result"]["already_had"] == 2
    assert after["message"].endswith("1 you deleted for good stay deleted.")
    assert len(library_ids(api)) == 2 and library_ids(api, "&archive=deleted") == []


def test_saves_taken_down_on_the_platform_have_their_own_part_of_the_archive(api: TestClient, svc: AppServices) -> None:
    one, two = add(svc, 1), add(svc, 2)
    with svc.db.connect() as conn:
        update_item(conn, one, safe_to_unsave=1)
        update_item(conn, two, status="failed", error="This video was deleted or isn't available any more.",
                    gone_at="2026-11-18T00:00:00Z", safe_to_unsave=1)
    assert library_ids(api) == [one]  # not in the Library, collections or the Unsave list
    assert library_ids(api, "&archive=gone") == [two]
    assert api.get("/api/archive").json() == {"deleted": 0, "unsaved": 0, "gone": 1}
    assert [item["id"] for item in api.get("/api/unsave").json()["items"]] == [one]
    assert api.get(f"/api/library/items?archive=gone").json()["items"][0]["gone"] is True


def test_clear_checklist_keeps_library_and_can_be_undone(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        save_id, _ = upsert_item(conn, NewItem("tiktok", "https://example.com/checklist"))
        update_item(conn, save_id, safe_to_unsave=1)
    assert api.get("/api/unsave").json()["left"] == 1
    assert api.post("/api/unsave/clear").json()["cleared"] == 1
    assert api.get("/api/unsave").json() == {"items": [], "left": 0}
    saved = api.get(f"/api/items/{save_id}").json()["item"]
    assert not saved["unsaved"] and not saved["deleted"]
    assert api.post("/api/undo").status_code == 200
    assert api.get("/api/unsave").json()["left"] == 1


def test_a_failed_save_can_be_marked_unavailable_and_undone(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        save_id, _ = upsert_item(conn, NewItem("tiktok", "https://example.com/unreadable"))
        update_item(conn, save_id, status="failed", error="Could not read")
    response = api.patch(f"/api/items/{save_id}", json={"unavailable": True})
    assert response.status_code == 200 and response.json()["gone"]
    assert not response.json()["unsaved"] and not response.json()["deleted"]
    assert library_ids(api, "&archive=gone") == [save_id]
    assert api.post("/api/undo").status_code == 200
    assert not api.get(f"/api/items/{save_id}").json()["item"]["gone"]


def test_archive_batch_only_changes_the_confirmed_platform_and_members(api, svc):
    from app.library import scope
    from app.search.agent import catalog
    assert all("/archive/batch" not in entry["path"] for entry in catalog(api.app))
    first, second = add(svc, 1), add(svc, 2)
    with svc.db.connect() as conn:
        foreign, _ = upsert_item(conn, NewItem("youtube", "https://example.com/watch"))
    for item_id in (first, foreign):
        api.patch(f"/api/items/{item_id}", json={"deleted": True})
    scope.choose(svc.settings, "tiktok")
    url = "/api/archive/batch/purge"
    preview = api.get(url).json()
    assert preview["count"] == 1
    api.patch(f"/api/items/{second}", json={"deleted": True})
    assert api.post(url, json={"token": preview["token"]}).status_code == 409
    restore = "/api/archive/batch/restore"
    assert api.post(restore, json={"token": api.get(restore).json()["token"]}).json() == {"count": 2}
    assert api.post("/api/undo").status_code == 200
    assert api.post(url, json={"token": api.get(url).json()["token"]}).json() == {"count": 2}
    scope.choose(svc.settings, None)
    assert library_ids(api, "&archive=deleted") == [foreign]
