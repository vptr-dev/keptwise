"""Settings -> Storage: listing what takes up space, and deleting it."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import storage
from app.ai.http import HttpError
from app.paths import move_old_folder
from app.services import AppServices
from tests.fakes import FakeNet

OLLAMA = "http://localhost:11434"


def entries_by_id(data: dict) -> dict[str, dict]:
    return {e["id"]: e for e in data["entries"]}


def test_folder_bytes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.bin").write_bytes(b"12345")
    (tmp_path / "y.bin").write_bytes(b"123")
    assert storage.folder_bytes(tmp_path) == 8
    assert storage.folder_bytes(tmp_path / "missing") == 0


def test_lists_models_and_files(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    net.on("GET", f"{OLLAMA}/api/tags", {"models": [
        {"name": "gemma4:12b", "size": 8_000_000_000},
        {"name": "llama9:1b", "size": 1_000_000_000},
    ]})
    small = svc.paths.models / "whisper" / "small"
    small.mkdir(parents=True)
    (small / "model.bin").write_bytes(b"x" * 100)
    (svc.paths.audio / "1.m4a").write_bytes(b"x" * 10)

    found = entries_by_id(api.get("/api/storage").json())
    assert found["ollama:gemma4:12b"]["bytes"] == 8_000_000_000
    assert found["ollama:gemma4:12b"]["in_use"] is True  # Ollama with gemma4:12b is the default
    assert found["ollama:llama9:1b"]["in_use"] is False
    assert found["speech:small"]["bytes"] == 100 and found["speech:small"]["in_use"] is True
    assert found["audio"]["bytes"] == 10
    assert found["database"]["can_delete"] is False


def test_ollama_not_running_lists_only_local_things(api: TestClient) -> None:
    found = entries_by_id(api.get("/api/storage").json())
    assert not any(key.startswith("ollama:") for key in found)
    assert "audio" in found


def test_delete_ollama_model(api: TestClient, net: FakeNet) -> None:
    net.on("GET", f"{OLLAMA}/api/tags", {"models": []})
    net.on("DELETE", f"{OLLAMA}/api/delete", None)
    assert api.delete("/api/storage/ollama:llama9:1b").status_code == 200
    sent = [r for r in net.requests if r["method"] == "DELETE"]
    assert sent[0]["json"] == {"model": "llama9:1b"}


def test_delete_ollama_error_is_explained(api: TestClient, net: FakeNet) -> None:
    net.on("DELETE", f"{OLLAMA}/api/delete", HttpError("HTTP 500", status=500))
    response = api.delete("/api/storage/ollama:gemma4:12b")
    assert response.status_code == 400 and "Ollama" in response.json()["detail"]


def test_delete_speech_model_and_audio(api: TestClient, svc: AppServices) -> None:
    tiny = svc.paths.models / "whisper" / "tiny"
    tiny.mkdir(parents=True)
    (tiny / "model.bin").write_bytes(b"x")
    (svc.paths.audio / "1.m4a").write_bytes(b"x")
    assert api.delete("/api/storage/speech:tiny").status_code == 200
    assert not tiny.exists()
    assert api.delete("/api/storage/audio").status_code == 200
    assert list(svc.paths.audio.iterdir()) == [] and svc.paths.audio.exists()


def test_refuses_odd_or_protected_entries(api: TestClient, svc: AppServices) -> None:
    assert api.delete("/api/storage/database").status_code == 400
    assert api.delete("/api/storage/speech:..").status_code == 400
    assert svc.paths.database.exists()


def test_waits_while_a_job_runs(api: TestClient, svc: AppServices) -> None:
    job_id = svc.jobs.create("enrich", "Transcripts", {})
    svc.jobs.update(job_id, status="running")
    response = api.delete("/api/storage/audio")
    assert response.status_code == 409 and "Transcripts" in response.json()["detail"]


def test_old_data_folder_is_renamed(tmp_path: Path) -> None:
    old, new = tmp_path / "SavesKnowledge", tmp_path / "Keptwise"
    old.mkdir()
    (old / "saves.db").write_bytes(b"db")
    assert move_old_folder(old, new) == new
    assert (new / "saves.db").read_bytes() == b"db" and not old.exists()
    # Nothing to move, or the new one already exists: just use the new one.
    assert move_old_folder(old, new) == new


def test_old_folder_left_alone_when_new_exists(tmp_path: Path) -> None:
    old, new = tmp_path / "SavesKnowledge", tmp_path / "Keptwise"
    old.mkdir()
    new.mkdir()
    assert move_old_folder(old, new) == new and old.exists()


def test_keys_saved_by_older_versions_move_to_the_new_name(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import keyring

    from app.ai.secrets import OLD_SERVICE_NAME, SERVICE_NAME, KeyringStore

    vault: dict[tuple[str, str], str] = {(OLD_SERVICE_NAME, "openai"): "sk-old"}
    monkeypatch.setattr(keyring, "get_password", lambda s, u: vault.get((s, u)))
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: vault.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "delete_password", lambda s, u: vault.pop((s, u)))
    store = KeyringStore()
    assert store.get("openai") == "sk-old"
    assert vault == {(SERVICE_NAME, "openai"): "sk-old"}
    assert store.get("anthropic") is None


def make_db(folder: Path, items: int) -> None:
    import sqlite3

    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "saves.db")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO items (id) VALUES (?)", [(i,) for i in range(1, items + 1)])
    conn.commit()
    conn.close()


def test_empty_new_folder_is_set_aside_for_the_real_one(tmp_path: Path) -> None:
    old, new = tmp_path / "SavesKnowledge", tmp_path / "Keptwise"
    make_db(old, 3)
    make_db(new, 0)  # e.g. made by a test run before the rename
    assert move_old_folder(old, new) == new
    assert not old.exists()
    aside = [p for p in tmp_path.iterdir() if p.name.startswith("Keptwise-empty-")]
    assert len(aside) == 1 and (aside[0] / "saves.db").exists()  # kept, not deleted
    from app.paths import has_saves

    assert has_saves(new)


def test_new_folder_with_saves_wins(tmp_path: Path) -> None:
    old, new = tmp_path / "SavesKnowledge", tmp_path / "Keptwise"
    make_db(old, 3)
    make_db(new, 1)
    assert move_old_folder(old, new) == new and old.exists()


def test_clear_my_data_backups_saves_or_everything(api: TestClient, svc: AppServices) -> None:
    from app.db.items_repo import NewItem, upsert_item

    def fill() -> None:
        with svc.db.connect() as conn:
            for n in range(3):
                upsert_item(conn, NewItem(platform="tiktok", url=f"https://www.tiktok.com/@a/video/{n}"))
        api.post("/api/collections", json={"name": "Trips"})
        api.post("/api/plans", json={"name": "Weekend"})
        (svc.paths.thumbnails / "1.jpg").write_bytes(b"x" * 10)
        backups = svc.paths.root / "backups"
        backups.mkdir(exist_ok=True)
        (backups / "saves-v1-old.db").write_bytes(b"y" * 20)

    fill()
    api.put("/api/ui", json={"theme": "dark"})
    before = api.get("/api/storage").json()
    assert before["saves"] == 3 and before["backups"] == 1 and before["backups_bytes"] == 20

    # Only the backups.
    after = api.post("/api/storage/clear", json={"what": "backups"}).json()
    assert after["cleared"] == {"backups": 1} and after["backups"] == 0 and after["saves"] == 3

    # The saves: everything saved or made goes, settings stay.
    after = api.post("/api/storage/clear", json={"what": "saves"}).json()
    assert after["cleared"] == {"saves": 3} and after["saves"] == 0
    assert api.get("/api/library/items").json()["total"] == 0
    assert api.get("/api/collections").json()["collections"] == []
    assert api.get("/api/plans").json()["plans"] == []
    assert not (svc.paths.thumbnails / "1.jpg").exists()
    assert api.get("/api/ui").json()["theme"] == "dark"
    assert [s["name"] for s in api.get("/api/collections").json()["spaces"]] == ["My saves"]

    # Everything at once, and the app still works afterwards.
    fill()
    after = api.post("/api/storage/clear", json={"what": "everything"}).json()
    assert after["cleared"] == {"saves": 3, "backups": 1} and after["saves"] == 0 and after["backups"] == 0
    assert api.post("/api/collections", json={"name": "New start"}).status_code == 200
    assert api.post("/api/storage/clear", json={"what": "the lot"}).status_code == 422
