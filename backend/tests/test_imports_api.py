"""Tests for the import routes and the "import" background job."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.imports import safe_parts
from app.importers.job import remove_old_uploads
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
