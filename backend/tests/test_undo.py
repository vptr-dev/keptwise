"""Undo and redo: every change made through the app can be taken back and put back."""

from __future__ import annotations

from typing import Any

from app.db.items_repo import NewItem, upsert_item
from app.services import AppServices


def add_saves(svc: AppServices, count: int) -> list[int]:
    ids = []
    with svc.db.connect() as conn:
        for number in range(count):
            item_id, _ = upsert_item(conn, NewItem(platform="tiktok", url=f"https://t/{number}", caption=f"save {number}"))
            ids.append(item_id)
    return ids


def names(api: Any) -> list[str]:
    return sorted(c["name"] for c in api.get("/api/collections").json()["collections"])


def links(svc: AppServices) -> list[tuple[int, int]]:
    with svc.db.connect() as conn:
        return sorted(tuple(r) for r in conn.execute("SELECT item_id, collection_id FROM item_collections"))


def test_nothing_to_undo_at_first(api: Any) -> None:
    assert api.get("/api/undo").json() == {"undo": None, "redo": None}
    assert api.post("/api/undo").status_code == 409


def test_a_new_collection_can_be_undone_and_redone(api: Any) -> None:
    made = api.post("/api/collections", json={"name": "Recipes"}).json()
    assert "Recipes" in names(api)
    assert api.get("/api/undo").json()["undo"]["label"] == "New collection"

    undone = api.post("/api/undo").json()
    assert undone["done"] == "New collection" and undone["redo"]["label"] == "New collection"
    assert "Recipes" not in names(api)

    api.post("/api/redo")
    after = api.get("/api/collections").json()["collections"]
    assert [c["id"] for c in after if c["name"] == "Recipes"] == [made["created_id"]]


def test_deleting_a_collection_with_saves_in_it_comes_back_whole(api: Any, svc: AppServices) -> None:
    ids = add_saves(svc, 3)
    collection = api.post("/api/collections", json={"name": "Trips"}).json()
    collection_id = collection["created_id"]
    api.post("/api/items/bulk", json={"item_ids": ids, "action": "add_to", "collection_id": collection_id})
    before = links(svc)
    assert len(before) == 3

    api.delete(f"/api/collections/{collection_id}")
    assert links(svc) == [] and "Trips" not in names(api)
    api.post("/api/undo")
    assert links(svc) == before and "Trips" in names(api)
    api.post("/api/redo")
    assert links(svc) == []


def test_steps_undo_in_order_and_a_new_change_clears_redo(api: Any, svc: AppServices) -> None:
    (item_id,) = add_saves(svc, 1)
    api.post(f"/api/items/{item_id}/tags", json={"name": "pasta"})
    tag_id = api.get("/api/tags").json()["tags"][0]["id"]
    api.patch(f"/api/tags/{tag_id}", json={"name": "dinner"})
    assert api.get("/api/undo").json()["undo"]["label"] == "Change tag"

    api.post("/api/undo")
    assert api.get("/api/tags").json()["tags"][0]["name"] == "pasta"
    api.post("/api/undo")
    assert api.get("/api/tags").json()["tags"] == [] or api.get(f"/api/library/items?tag=pasta").json()["total"] == 0

    api.post("/api/redo")  # the tag is back on the save
    api.post("/api/collections", json={"name": "New thing"})  # a new change: what was undone can't be redone
    assert api.get("/api/undo").json()["redo"] is None


def test_background_work_is_not_undone(api: Any, svc: AppServices) -> None:
    (item_id,) = add_saves(svc, 1)
    api.patch(f"/api/items/{item_id}", json={"done": True})
    with svc.db.connect() as conn:  # like a background job: not recorded
        conn.execute("UPDATE items SET title = 'From the transcript job' WHERE id = ?", (item_id,))
    api.post("/api/undo")
    with svc.db.connect() as conn:
        row = conn.execute("SELECT title, done_at FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["title"] == "From the transcript job"  # untouched
    assert row["done_at"] is None  # the user's change was undone


def test_a_step_that_no_longer_fits_is_dropped_with_a_clear_message(api: Any, svc: AppServices) -> None:
    made = api.post("/api/collections", json={"name": "Gym"}).json()
    collection_id = made["created_id"]
    api.delete(f"/api/collections/{collection_id}")
    with svc.db.connect() as conn:  # something else took the name meanwhile
        conn.execute("INSERT INTO collections (name, space_id) SELECT 'Gym', id FROM spaces LIMIT 1")
    response = api.post("/api/undo")
    assert response.status_code == 409 and "can't be undone any more" in response.json()["detail"]
    assert api.get("/api/undo").json()["undo"]["label"] == "New collection"  # the one before is still there
