"""Spaces, collections inside collections, and the safety copy made before
an update changes the database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.sorting import collections
from app.ai.sorting.settings import SortingSettings, load, save
from app.db.connection import Database
from app.db.items_repo import NewItem, upsert_item
from app.db.migrations import MIGRATIONS, schema_version
from app.services import AppServices


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "saves.db")


def test_collections_sit_inside_each_other(db: Database) -> None:
    with db.connect() as conn:
        food = collections.create(conn, "Food")
        desserts = collections.create(conn, "Desserts", parent_id=food)
        cakes = collections.create(conn, "Cakes", parent_id=desserts)
        travel = collections.create(conn, "Travel")
        item, _ = upsert_item(conn, NewItem("tiktok", "https://example.com/v/1"))
        collections.add_by_user(conn, item, cakes)
        rows = {row["name"]: row for row in collections.list_all(conn)}
        assert [row["name"] for row in collections.list_all(conn)] == ["Food", "Desserts", "Cakes", "Travel"]
        assert (rows["Cakes"]["path"], rows["Cakes"]["depth"], rows["Cakes"]["parent_id"]) == ("Food / Desserts / Cakes", 2, desserts)
        assert (rows["Food"]["count"], rows["Food"]["total"], rows["Food"]["has_children"]) == (0, 1, True)
        assert collections.descendants(conn, food) == [food, desserts, cakes]

        with pytest.raises(ValueError, match="inside itself"):
            collections.place(conn, food, cakes, 0)
        collections.place(conn, desserts, travel, 0)  # Cakes comes along
        rows = {row["name"]: row for row in collections.list_all(conn)}
        assert rows["Cakes"]["path"] == "Travel / Desserts / Cakes"

        collections.delete(conn, desserts)  # what's inside moves up a level; the save stays in Cakes
        rows = {row["name"]: row for row in collections.list_all(conn)}
        assert rows["Cakes"]["parent_id"] == travel and rows["Cakes"]["count"] == 1


def test_collections_go_five_levels_deep_at_most(db: Database) -> None:
    with db.connect() as conn:
        parent = None
        for level in range(collections.MAX_DEPTH):
            parent = collections.create(conn, f"Level {level + 1}", parent_id=parent)
        with pytest.raises(ValueError, match="5 levels deep"):
            collections.create(conn, "Too deep", parent_id=parent)
        other = collections.create(conn, "Other")
        with pytest.raises(ValueError, match="5 levels deep"):
            collections.place(conn, collections.find(conn, "Level 1")["id"], other, 0)


def test_spaces_hold_their_own_collections(db: Database) -> None:
    with db.connect() as conn:
        first = collections.default_space(conn)
        assert [s["name"] for s in collections.spaces(conn)] == ["My saves"]
        work = collections.create_space(conn, "Work")
        with pytest.raises(ValueError, match="already a space"):
            collections.create_space(conn, "work")
        food = collections.create(conn, "Food")
        desserts = collections.create(conn, "Desserts", parent_id=food)
        decks = collections.create(conn, "Decks", space_id=work)
        assert collections.count(conn, first) == 2 and collections.count(conn, work) == 1

        # A space holds up to 50; another space still has room.
        for n in range(collections.MAX_COLLECTIONS - 2):
            collections.create(conn, f"Topic {n}")
        with pytest.raises(ValueError, match="most a space can hold"):
            collections.create(conn, "One too many")
        collections.create(conn, "Fits here", space_id=work)

        # Moving a collection to another space takes what's inside it along.
        collections.place(conn, food, None, 0, space_id=work)
        rows = {row["name"]: row for row in collections.list_all(conn)}
        assert rows["Food"]["space_id"] == work and rows["Desserts"]["space_id"] == work
        assert rows["Desserts"]["parent_id"] == food

        # Deleting a space moves its collections to the first other one.
        collections.update_space(conn, work, name="Job", color="teal")
        with pytest.raises(ValueError, match="don't fit"):
            collections.delete_space(conn, first)  # 48 + 4 > 50
        collections.delete(conn, decks)
        collections.delete(conn, collections.find(conn, "Fits here")["id"])
        assert collections.delete_space(conn, first) == work
        assert [s["name"] for s in collections.spaces(conn)] == ["Job"]
        assert collections.count(conn, work) == 50 and desserts in collections.descendants(conn, food)
        with pytest.raises(ValueError, match="only space"):
            collections.delete_space(conn, work)


def test_space_and_folder_routes(api: TestClient, svc: AppServices) -> None:
    listed = api.get("/api/collections").json()
    assert [s["name"] for s in listed["spaces"]] == ["My saves"]
    assert (listed["limit"], listed["space_limit"], listed["depth_limit"]) == (50, 8, 5)
    first = listed["spaces"][0]["id"]
    food = next(c["id"] for c in listed["collections"] if c["name"] == "Food")

    made = api.post("/api/spaces", json={"name": "Work"}).json()
    work = made["created_space"]
    assert api.post("/api/spaces", json={"name": "work"}).status_code == 400
    renamed = api.patch(f"/api/spaces/{work}", json={"name": "Job", "index": 0}).json()
    assert [s["name"] for s in renamed["spaces"]] == ["Job", "My saves"]

    inner = api.post("/api/collections", json={"name": "Desserts", "parent_id": food}).json()
    desserts = inner["created_id"]
    row = next(c for c in inner["collections"] if c["id"] == desserts)
    assert (row["path"], row["space_id"]) == ("Food / Desserts", first)
    deck = api.post("/api/collections", json={"name": "Decks", "space_id": work}).json()["created_id"]

    # Picked together, a collection and the one inside it move as one.
    moved = api.post("/api/collections/bulk", json={"ids": [food, desserts], "action": "move", "space_id": work}).json()
    rows = {c["name"]: c for c in moved["collections"]}
    assert rows["Food"]["space_id"] == work and rows["Desserts"]["parent_id"] == food
    inside = api.post("/api/collections/bulk", json={"ids": [deck], "action": "move", "parent_id": desserts}).json()
    assert next(c for c in inside["collections"] if c["id"] == deck)["path"] == "Food / Desserts / Decks"
    assert api.post(f"/api/collections/{food}/place", json={"parent_id": deck, "index": 0}).status_code == 400

    gone = api.post("/api/collections/bulk", json={"ids": [desserts], "action": "delete"}).json()
    assert next(c for c in gone["collections"] if c["id"] == deck)["parent_id"] == food

    deleted = api.delete(f"/api/spaces/{first}").json()  # its collections move to the other space
    assert deleted["moved_to"] == work and all(c["space_id"] == work for c in deleted["collections"])
    assert api.delete(f"/api/spaces/{work}").status_code == 400  # the only one left


def test_a_folder_shows_its_own_saves_or_everything_inside(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        food = collections.create(conn, "Meals")
        cakes = collections.create(conn, "Cakes", parent_id=food)
        one, _ = upsert_item(conn, NewItem("tiktok", "https://example.com/v/1"))
        two, _ = upsert_item(conn, NewItem("tiktok", "https://example.com/v/2"))
        collections.add_by_user(conn, one, food)
        collections.add_by_user(conn, two, cakes)
    everything = api.get(f"/api/library/items?collection_id={food}").json()
    assert everything["total"] == 2
    own = api.get(f"/api/library/items?collection_id={food}&include_sub=false").json()
    assert [i["id"] for i in own["items"]] == [one]


def test_platform_collections_transfer_in_one_go(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        for n, where in enumerate(["Recipes, Watch later", "recipes", None]):
            item_id, _ = upsert_item(conn, NewItem(platform="youtube", url=f"https://y/{n}", platform_collection=where))
            if where == "Recipes, Watch later":
                conn.execute("UPDATE items SET platform_collections_json = ? WHERE id = ?",
                             ('["Recipes", "Watch later"]', item_id))
        conn.execute(
            "INSERT INTO jobs (kind, title, status, result_json) VALUES ('import', 'Import', 'done', ?)",
            ('{"platforms": [{"platform": "tiktok", "collections": ["Gym", "Food"]}]}',),
        )
        holder = collections.create(conn, "From my apps")
        collections.create(conn, "Food")
    done = api.post("/api/platform-collections/transfer", json={"parent_id": holder}).json()
    assert (done["linked"], done["made"], done["filed"], done["no_room"]) == (4, 3, 3, 0)  # "Food" already existed
    assert all(link["collection_id"] is not None and link["mode"] == "auto" for link in done["links"])
    rows = {c["name"]: c for c in api.get("/api/collections").json()["collections"]}
    assert rows["Recipes"]["path"] == "From my apps / Recipes" and rows["Recipes"]["count"] == 2
    again = api.post("/api/platform-collections/transfer", json={}).json()
    assert again["linked"] == 0


def test_filing_by_the_ai_is_off_until_switched_on(svc: AppServices) -> None:
    assert load(svc.settings).auto_sort is False
    save(svc.settings, SortingSettings(auto_sort=True))
    assert load(svc.settings).auto_sort is True


def test_saves_missing_sound_only_because_of_a_403_go_back_in_the_queue(tmp_path: Path) -> None:
    old = tmp_path / "saves.db"
    conn = sqlite3.connect(old)
    for number, script in enumerate(MIGRATIONS[:12], start=1):
        conn.executescript("BEGIN;" + chr(10) + script + chr(10) + f"PRAGMA user_version = {number}; COMMIT;")
    rows = [
        ("a", "Got the details, but not the sound. TikTok said no (HTTP Error 403: Forbidden)"),
        ("b", "Got the details, but not the sound. This video has no sound."),
        ("c", None),
    ]
    for word, error in rows:
        conn.execute("INSERT INTO items (platform, url, saved_at, status, error) VALUES "
                     "('tiktok', ?, '2024-01-01T00:00:00Z', 'enriched', ?)", (f"https://t/{word}", error))
    conn.commit()
    conn.close()
    with Database(old).connect() as conn:
        status = {row[0]: row[1] for row in conn.execute("SELECT url, status FROM items")}
    assert status == {"https://t/a": "imported", "https://t/b": "enriched", "https://t/c": "enriched"}


def test_a_copy_is_kept_before_an_update_changes_the_database(tmp_path: Path) -> None:
    path = tmp_path / "saves.db"
    assert Database(path).backup_made is None  # brand new: nothing to keep
    assert Database(path).backup_made is None  # already up to date

    # A file as the version before this one left it: every step but the last.
    old = tmp_path / "old" / "saves.db"
    old.parent.mkdir()
    conn = sqlite3.connect(old)
    for number, script in enumerate(MIGRATIONS[:-1], start=1):
        conn.executescript("BEGIN;" + chr(10) + script + chr(10) + f"PRAGMA user_version = {number}; COMMIT;")
    conn.execute("INSERT INTO collections (name) VALUES ('Keep me')")
    conn.commit()
    conn.close()

    updated = Database(old)
    assert updated.backup_made is not None
    with updated.connect() as conn:
        assert schema_version(conn) == len(MIGRATIONS)
        assert [row["name"] for row in collections.list_all(conn)] == ["Keep me"]
    copies = list((old.parent / "backups").glob(f"saves-v{len(MIGRATIONS) - 1}-*.db"))
    assert len(copies) == 1
    copy = sqlite3.connect(copies[0])
    assert copy.execute("SELECT name FROM collections").fetchone()[0] == "Keep me"
    assert schema_version(copy) == len(MIGRATIONS) - 1
    copy.close()


def test_a_collection_can_carry_an_icon(api: TestClient) -> None:
    made = api.post("/api/collections", json={"name": "Trips"}).json()
    trips = next(c for c in made["collections"] if c["name"] == "Trips")
    assert trips["icon"] is None
    after = api.patch(f"/api/collections/{trips['id']}", json={"icon": "plane"}).json()
    assert next(c for c in after["collections"] if c["id"] == trips["id"])["icon"] == "plane"
    assert api.patch(f"/api/collections/{trips['id']}", json={"icon": "dragon"}).status_code == 400
    # Renaming leaves the icon alone; an empty icon makes it a plain folder again.
    after = api.patch(f"/api/collections/{trips['id']}", json={"name": "Journeys"}).json()
    assert next(c for c in after["collections"] if c["id"] == trips["id"])["icon"] == "plane"
    after = api.patch(f"/api/collections/{trips['id']}", json={"icon": ""}).json()
    assert next(c for c in after["collections"] if c["id"] == trips["id"])["icon"] is None


def test_your_own_picture_on_a_collection(api: TestClient, svc: AppServices) -> None:
    import base64
    import io

    from PIL import Image

    made = api.post("/api/collections", json={"name": "Trips"}).json()
    trips = next(c for c in made["collections"] if c["name"] == "Trips")["id"]
    big = io.BytesIO()
    Image.new("RGB", (900, 600), "red").save(big, "JPEG")
    data = "data:image/jpeg;base64," + base64.b64encode(big.getvalue()).decode()
    after = api.post(f"/api/collections/{trips}/icon", json={"data": data}).json()
    assert next(c for c in after["collections"] if c["id"] == trips)["icon"].startswith("custom:")
    shown = api.get(f"/api/collections/{trips}/icon")
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(shown.content)) as kept:
        assert max(kept.size) == 192  # shrunk

    # Not a picture: refused, and nothing changes.
    junk = "data:image/png;base64," + base64.b64encode(b"this is not a picture at all").decode()
    assert api.post(f"/api/collections/{trips}/icon", json={"data": junk}).status_code == 400
    assert api.post(f"/api/collections/{trips}/icon", json={"data": "data:text/plain;base64,aGVsbG8gdGhlcmU="}).status_code == 400
    assert api.post("/api/collections/9999/icon", json={"data": data}).status_code == 404

    # Choosing a ready-made icon (or none) drops the picture file.
    api.patch(f"/api/collections/{trips}", json={"icon": "plane"})
    assert api.get(f"/api/collections/{trips}/icon").status_code == 404
    assert not (svc.paths.collection_icons / f"{trips}.png").exists()


def test_the_simpler_sorting_update_keeps_the_users_data(tmp_path: Path) -> None:
    """Migration 15: taken-down saves move to the Archive, notes that say
    "please provide a video" go back to waiting, the "unsorted" tag and
    Needs review go, and the AI stops filing and tagging by itself."""
    old = tmp_path / "saves.db"
    conn = sqlite3.connect(old)
    for number, script in enumerate(MIGRATIONS[:14], start=1):
        conn.executescript("BEGIN;" + chr(10) + script + chr(10) + f"PRAGMA user_version = {number}; COMMIT;")
    add = "INSERT INTO items (platform, url, status, error, needs_review, safe_to_unsave, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
    conn.execute(add, ("tiktok", "https://t/gone", "failed", "This video was deleted or isn't available any more.", 0, 0, None))
    conn.execute(add, ("tiktok", "https://t/private", "failed", "This video is private, so only the person who posted it can see it.", 0, 0, None))
    conn.execute(add, ("tiktok", "https://t/junk", "processed", None, 1, 1, None))
    conn.execute(add, ("tiktok", "https://t/good", "processed", None, 0, 1, None))
    conn.execute(add, ("tiktok", "https://t/binned", "imported", None, 0, 0, "2026-01-01T00:00:00Z"))
    conn.execute("INSERT INTO ai_results (item_id, title, summary, new_collection) VALUES "
                 "(3, 'No video provided', 'Please provide a video, transcript, or caption.', 'Car stuff')")
    conn.execute("INSERT INTO ai_results (item_id, title, summary, new_collection) VALUES (4, 'Carbonara', 'Pasta.', 'Cars')")
    conn.execute("INSERT INTO collections (name) VALUES ('Food')")
    conn.execute("INSERT INTO item_collections (item_id, collection_id, source) VALUES (3, 1, 'ai'), (4, 1, 'user')")
    conn.execute("INSERT INTO tags (name) VALUES ('unsorted'), ('pasta')")
    conn.execute("INSERT INTO item_tags (item_id, tag_id, source) VALUES (3, 1, 'auto'), (4, 2, 'user'), (3, 2, 'ai')")
    conn.execute("INSERT INTO settings (key, value_json) VALUES ('sorting', ?)",
                 ('{"auto_sort": true, "auto_tag": true, "mode": "my_list_plus_ideas", "no_collection_tag": "unsorted", '
                  '"safe_to_unsave": "done", "max_collections": 3}',))
    conn.commit()
    conn.close()

    with Database(old).connect() as conn:
        items = {row["url"].rsplit("/", 1)[1]: dict(row) for row in conn.execute("SELECT * FROM items")}
        assert items["gone"]["gone_at"] and not items["private"]["gone_at"]
        assert (items["junk"]["status"], items["junk"]["safe_to_unsave"], items["junk"]["needs_review"]) == ("enriched", 0, 0)
        assert items["good"]["status"] == "processed" and items["binned"]["safe_to_unsave"] == 1
        assert [row[0] for row in conn.execute("SELECT item_id FROM ai_results")] == [4]
        assert conn.execute("SELECT new_collection FROM ai_results").fetchone()[0] is None
        assert [tuple(row) for row in conn.execute("SELECT item_id, collection_id, source FROM item_collections")] == [(4, 1, "user")]
        assert [row[0] for row in conn.execute("SELECT name FROM tags")] == ["pasta"]
        assert [tuple(row) for row in conn.execute("SELECT item_id, source FROM item_tags")] == [(4, "user")]
        sorting = json.loads(conn.execute("SELECT value_json FROM settings WHERE key = 'sorting'").fetchone()[0])
    assert sorting == {"auto_sort": False, "auto_tag": False, "mode": "my_list", "max_collections": 3}
