"""Tests for the import routes and the "import" background job."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.sorting import collections
from app.api.imports import safe_parts
from app.importers import pasted
from app.db.items_repo import NewItem, upsert_item
from app.importers.job import remove_old_uploads, save_batch
from app.services import AppServices
from tests.test_importers import SAMPLES, zip_folder
from tests.test_jobs import wait_for_status


def upload(api: TestClient, files: dict[str, bytes], name: str = "export") -> dict[str, Any]:
    """Do what the window does: create an upload, send files, start the job."""
    created = api.post("/api/imports").json()
    upload_id = created["upload_id"]
    for path, content in files.items():
        response = api.put(f"/api/imports/{upload_id}/files", params={"path": path}, content=content)
        assert response.status_code == 200, response.text
        assert response.json()["bytes"] == len(content)
    response = api.post(f"/api/imports/{upload_id}/start", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def run_import(api: TestClient, svc: AppServices, files: dict[str, bytes]) -> dict[str, Any]:
    job = upload(api, files)
    return wait_for_status(svc, job["id"], "done", "failed")


def item_count(svc: AppServices) -> int:
    with svc.db.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])


@pytest.mark.parametrize(("platform", "url", "other"), [
    ("tiktok", "https://www.tiktok.com/@chef/video/7300000000000000001", "https://www.tiktokv.com/share/video/7300000000000000001/"),
    ("youtube", "https://youtu.be/dQw4w9WgXcQ?si=sample", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
    ("instagram", "https://www.instagram.com/reel/CfakeReel02/?igsh=sample", "https://www.instagram.com/p/CfakeReel02/"),
    ("facebook", "https://www.facebook.com/creator/videos/123456", "https://m.facebook.com/watch/?v=123456"),
])
def test_import_single_link(api, svc, platform, url, other):
    with svc.db.connect() as conn:
        inbox = collections.ensure(conn, "Inbox")
    assert api.put("/api/platform-collections/default", json={"platform": platform, "collection_id": inbox}).status_code == 200
    route = "/api/imports/link"
    assert api.post(route, json={"url": url}).json()["status"] == "added"
    assert api.post(route, json={"url": other}).json()["status"] == "already_had"
    with svc.db.connect() as conn:
        row = conn.execute("SELECT id, platform, status FROM items").fetchone()
        assert (row["platform"], row["status"]) == (platform, "imported")
        assert conn.execute("SELECT collection_id FROM item_collections WHERE item_id = ?", (row["id"],)).fetchone()[0] == inbox
    item_path = f"/api/items/{row['id']}"
    assert api.patch(item_path, json={"deleted": True}).status_code == 200
    assert api.post(route, json={"url": other}).json()["status"] == "already_had"
    assert api.delete(item_path).status_code == 200
    assert api.post(route, json={"url": other}).json()["status"] == "deleted_before"
    assert item_count(svc) == 0
    assert api.post(route, json={"url": other, "reimport": True}).json()["status"] == "added"
    assert item_count(svc) == 1


def test_short_links_only_follow_supported_same_platform_redirects(api, monkeypatch):
    requests = []

    def redirect(url):
        requests.append(url)
        if url.endswith("/video/"):
            return "http://127.0.0.1/private"
        return "https://www.tiktok.com/@chef/video/7300000000000000001"

    monkeypatch.setattr(pasted, "_redirect", redirect)
    route = "/api/imports/link"
    assert api.post(route, json={"url": "https://vm.tiktok.com/token/"}).json()["status"] == "added"
    assert api.post(route, json={"url": "https://vm.tiktok.com/video/"}).status_code == 400
    for url in ("https://www.tiktok.com.evil.example/t/token", "https://www.youtube.com/@creator",
                "https://www.facebook.com/profile.php?id=123", "https://www.tiktok.com:123/t/token"):
        assert api.post(route, json={"url": url}).status_code == 400
    assert requests == ["https://vm.tiktok.com/token/", "https://vm.tiktok.com/video/"]


def test_create_upload_says_which_files_to_send(api: TestClient) -> None:
    created = api.post("/api/imports").json()
    assert len(created["upload_id"]) == 32
    assert "user_data_tiktok.json" in created["wanted_names"]
    assert "saved_posts.json" in created["wanted_names"]
    assert created["wanted_extensions"] == [".zip", ".csv"]


def test_tiktok_zip_imports_and_reimport_adds_no_duplicates(
    api: TestClient, svc: AppServices, tmp_path: Path
) -> None:
    archive = zip_folder(SAMPLES / "tiktok_json", tmp_path / "tiktok.zip").read_bytes()

    first = run_import(api, svc, {"tiktok.zip": archive})
    assert first["status"] == "done", first
    assert first["title"] == "Import export"
    assert first["result"]["new"] == 3
    assert first["message"] == "Imported 3 new saves from TikTok."
    tiktok = first["result"]["platforms"][0]
    assert tiktok["name"] == "TikTok"
    assert "Skipped 2 liked videos: likes aren't saves." in tiktok["notes"]
    assert item_count(svc) == 3

    again = run_import(api, svc, {"tiktok.zip": archive})
    assert again["status"] == "done"
    assert again["result"]["new"] == 0
    assert again["result"]["already_had"] == 3
    assert again["message"] == "Nothing new: all 3 saves from TikTok were already in your library."
    assert item_count(svc) == 3

    # The same saves in TXT format are also recognised as the same videos.
    txt = (SAMPLES / "tiktok_txt" / "Activity" / "Favorite Videos.txt").read_bytes()
    third = run_import(api, svc, {"Activity/Favorite Videos.txt": txt})
    assert third["result"]["new"] == 1  # only video ...004 is new
    assert item_count(svc) == 4


def test_imported_items_are_stored_with_their_details(api: TestClient, svc: AppServices) -> None:
    folder = SAMPLES / "instagram"
    files = {file.relative_to(folder).as_posix(): file.read_bytes() for file in folder.rglob("*.json")}
    job = run_import(api, svc, files)
    assert job["result"]["platforms"][0]["collections"] == ["Recipes 🍝", "Japan trip"]
    with svc.db.connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE external_id = 'CfakeReel02'").fetchone()
    assert row["platform"] == "instagram"
    assert row["url"] == "https://www.instagram.com/p/CfakeReel02/"
    assert row["author"] == "café_lisboa"
    assert row["platform_collection"] == "Recipes 🍝"
    assert row["status"] == "imported"


def test_tiktok_destination_is_for_new_saves_only(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        inbox = collections.ensure(conn, "TikTok Inbox")
    first = (SAMPLES / "tiktok_json" / "user_data_tiktok.json").read_bytes()
    run_import(api, svc, {"user_data_tiktok.json": first})
    destination = {"platform": "tiktok", "collection_id": inbox}
    update = api.put("/api/platform-collections/default", json=destination)
    assert update.status_code == 200
    assert next(d for d in update.json()["import_destinations"] if d["platform"] == "tiktok")["collection_id"] == inbox

    txt = (SAMPLES / "tiktok_txt" / "Activity" / "Favorite Videos.txt").read_bytes()
    result = run_import(api, svc, {"Favorite Videos.txt": txt})["result"]
    assert (result["new"], result["platforms"][0]["filed"]) == (1, 1)
    with svc.db.connect() as conn:
        filed = conn.execute("SELECT item_id FROM item_collections WHERE collection_id = ?", (inbox,)).fetchone()[0]
        collections.remove(conn, filed, inbox)
    assert run_import(api, svc, {"Favorite Videos.txt": txt})["result"]["platforms"][0]["filed"] == 0


def test_known_membership_routes_new_and_newly_discovered_saves(api: TestClient, svc: AppServices) -> None:
    with svc.db.connect() as conn:
        inbox = collections.ensure(conn, "YouTube Inbox")
        food = collections.ensure(conn, "Recipes")
    assert api.put("/api/platform-collections/default", json={"platform": "youtube", "collection_id": inbox}).status_code == 200
    assert api.put("/api/platform-collections", json={
        "platform": "youtube", "name": "Cooking, quick", "collection_id": food,
    }).status_code == 200

    run_import(api, svc, {"Later-videos.csv": b"Video ID\nAbCdEfGhI01\n"})
    recipes = {"Cooking, quick-videos.csv": b"Video ID\nAbCdEfGhI01\nAbCdEfGhI02\n"}
    assert run_import(api, svc, recipes)["result"]["platforms"][0]["filed"] == 2
    with svc.db.connect() as conn:
        first, second = conn.execute("SELECT id, platform_collection FROM items ORDER BY id").fetchall()
        assert first["platform_collection"] == "Later, Cooking, quick"
        assert {link["id"] for link in collections.links_of(conn, first["id"])} == {inbox, food}
        assert {link["id"] for link in collections.links_of(conn, second["id"])} == {food}
        collections.remove(conn, first["id"], food)
    assert run_import(api, svc, recipes)["result"]["platforms"][0]["filed"] == 0
    by_name = {link["name"]: link for link in api.get("/api/platform-collections").json()["links"]}
    assert by_name["Cooking, quick"]["count"] == 2 and "Cooking" not in by_name and "quick" not in by_name


def test_unzipped_folder_with_all_four_platforms(api: TestClient, svc: AppServices) -> None:
    files = {
        f"{name}/{file.relative_to(SAMPLES / name).as_posix()}": file.read_bytes()
        for name in ("tiktok_json", "instagram", "facebook", "youtube")
        for file in (SAMPLES / name).rglob("*")
        if file.is_file()
    }
    job = run_import(api, svc, files)
    assert job["status"] == "done", job
    found = {platform["platform"]: platform["new"] for platform in job["result"]["platforms"]}
    assert found == {"tiktok": 3, "youtube": 4, "instagram": 4, "facebook": 3}
    assert job["message"] == "Imported 14 new saves from TikTok, YouTube, Instagram and Facebook."

    summary = api.get("/api/imports/summary").json()
    assert summary["total"] == 14
    assert {row["platform"]: row["count"] for row in summary["platforms"]} == found


def test_upload_copy_is_deleted_after_import(api: TestClient, svc: AppServices, tmp_path: Path) -> None:
    archive = zip_folder(SAMPLES / "tiktok_json", tmp_path / "t.zip").read_bytes()
    job = run_import(api, svc, {"t.zip": archive})
    assert not (svc.paths.imports / job["params"]["upload_id"]).exists()


def test_files_without_saves_fail_with_a_clear_reason(api: TestClient, svc: AppServices) -> None:
    job = run_import(api, svc, {"holiday.txt": b"just some notes"})
    assert job["status"] == "failed"
    assert "Couldn't find saved items" in job["error"]


def test_start_without_files_is_refused(api: TestClient) -> None:
    upload_id = api.post("/api/imports").json()["upload_id"]
    response = api.post(f"/api/imports/{upload_id}/start")
    assert response.status_code == 400
    assert "No files arrived" in response.json()["detail"]


def test_unknown_upload_ids_are_refused(api: TestClient) -> None:
    assert api.put("/api/imports/not-an-id/files", params={"path": "a.json"}, content=b"x").status_code == 404
    assert api.put("/api/imports/..%2F..%2Fx/files", params={"path": "a.json"}, content=b"x").status_code >= 400
    assert api.post(f"/api/imports/{'0' * 32}/start").status_code == 404


@pytest.mark.parametrize(
    "path",
    ["../escape.json", "..\\..\\Windows\\x.json", "C:\\x.json", "a/CON.json", "", "a/b./c.json", "x?.json"],
)
def test_unsafe_file_names_are_refused(api: TestClient, svc: AppServices, path: str) -> None:
    upload_id = api.post("/api/imports").json()["upload_id"]
    response = api.put(f"/api/imports/{upload_id}/files", params={"path": path}, content=b"x")
    assert response.status_code in (400, 422), response.text
    assert not (svc.paths.root / "escape.json").exists()


def test_safe_parts_keeps_normal_names() -> None:
    assert safe_parts("Takeout\\YouTube and YouTube Music/playlists/Watch later-videos.csv") == [
        "Takeout",
        "YouTube and YouTube Music",
        "playlists",
        "Watch later-videos.csv",
    ]
    assert safe_parts("/./Activity//Favorite Videos.txt") == ["Activity", "Favorite Videos.txt"]


def test_discarding_an_upload_deletes_its_files(api: TestClient, svc: AppServices) -> None:
    upload_id = api.post("/api/imports").json()["upload_id"]
    api.put(f"/api/imports/{upload_id}/files", params={"path": "a.json"}, content=b"{}")
    assert api.delete(f"/api/imports/{upload_id}").status_code == 204
    assert not (svc.paths.imports / upload_id).exists()


def test_old_leftover_uploads_are_removed(tmp_path: Path) -> None:
    old = tmp_path / ("a" * 32)
    new = tmp_path / ("b" * 32)
    old.mkdir()
    new.mkdir()
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    remove_old_uploads(tmp_path)
    assert not old.exists() and new.exists()


def test_legacy_comma_label_waits_for_exact_export_membership(api, svc):
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with svc.db.connect() as conn:
        upsert_item(conn, NewItem("youtube", url, platform_collection="Work, home"))
    before = api.get("/api/platform-collections").json()
    assert before["links"] == [] and before["unconfirmed_memberships"] == 1
    save_batch(svc.db, "youtube", [NewItem("youtube", url, platform_collection="Work, home",
                                         platform_collections=("Work, home",))])
    after = api.get("/api/platform-collections").json()
    assert after["unconfirmed_memberships"] == 0
    assert [(link["name"], link["count"]) for link in after["links"]] == [("Work, home", 1)]
