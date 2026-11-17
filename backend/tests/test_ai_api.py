"""Tests for AI settings: switching, keys, testing, and Ollama downloads."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.ollama_models import make_pull_handler
from app.ai.secrets import MemoryKeyStore
from app.services import AppServices
from tests.fakes import FakeNet

OLLAMA = "http://localhost:11434"
GB = 1_000_000_000


@pytest.fixture(autouse=True)
def plenty_of_disk_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """Downloads check free space; don't let this PC's real disk decide tests."""
    monkeypatch.setattr("app.api.ai.free_disk_bytes", lambda _folder: 500 * GB)


def ollama_running(net: FakeNet, models: list[str]) -> None:
    net.on("GET", f"{OLLAMA}/api/version", {"version": "0.40.15"})
    net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": m} for m in models]})


def wait_job(svc: AppServices, job_id: int, *statuses: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = svc.jobs.get(job_id)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job stuck: {svc.jobs.get(job_id)}")


def test_defaults_are_ollama_and_gemma(api: TestClient) -> None:
    overview = api.get("/api/ai").json()
    assert overview["current"] == "ollama"
    assert overview["current_kind"] == "local"
    assert overview["setup_done"] is False
    ollama = next(p for p in overview["providers"] if p["id"] == "ollama")
    assert ollama["model"] == "gemma4:12b"


def test_switch_local_cloud_local_without_restart(api: TestClient, net: FakeNet) -> None:
    net.on("POST", f"{OLLAMA}/api/chat", {"message": {"content": "from ollama"}})
    net.on("POST", "https://api.anthropic.com/v1/messages", {"content": [{"type": "text", "text": "from claude"}]})
    net.on("GET", "https://api.anthropic.com/v1/models", {"data": [{"id": "claude-haiku-5-5"}]})
    ollama_running(net, ["gemma4:12b"])

    assert api.post("/api/ai/providers/ollama/test").json()["ok"] is True

    api.put("/api/ai/providers/anthropic/key", json={"key": "sk-ant-secret"})
    switched = api.put("/api/ai/current", json={"provider": "anthropic"}).json()
    assert switched["current"] == "anthropic" and switched["current_kind"] == "cloud"
    result = api.post("/api/ai/providers/anthropic/test").json()
    assert result["ok"] is True and "from claude" in result["message"]

    back = api.put("/api/ai/current", json={"provider": "ollama"}).json()
    assert back["current"] == "ollama"
    # The Claude key is still saved, so switching back is instant.
    claude = next(p for p in back["providers"] if p["id"] == "anthropic")
    assert claude["key_saved"] is True


def test_keys_go_to_key_store_not_database(api: TestClient, svc: AppServices, keys: MemoryKeyStore) -> None:
    api.put("/api/ai/providers/openai/key", json={"key": "sk-abcdef1234"})
    assert keys.get("openai") == "sk-abcdef1234"
    openai = next(p for p in api.get("/api/ai").json()["providers"] if p["id"] == "openai")
    assert openai["key_hint"] == "••••1234"
    assert "sk-abcdef1234" not in str(svc.settings.all())

    api.delete("/api/ai/providers/openai/key")
    assert keys.get("openai") is None


def test_listing_models_picks_a_default(api: TestClient, net: FakeNet) -> None:
    api.put("/api/ai/providers/openai/key", json={"key": "sk-1"})
    net.on("GET", "https://api.openai.com/v1/models", {"data": [{"id": "gpt-big"}, {"id": "gpt-mini"}]})
    result = api.get("/api/ai/providers/openai/models").json()
    assert result == {"models": ["gpt-big", "gpt-mini"], "model": "gpt-mini"}


def test_errors_come_back_as_readable_messages(api: TestClient) -> None:
    response = api.get("/api/ai/providers/openai/models")
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Add your OpenAI API key in Settings first.",
        "code": "missing_key",
    }


def test_ready_check_spots_missing_model(api: TestClient, net: FakeNet) -> None:
    ollama_running(net, [])
    result = api.get("/api/ai/ready").json()
    assert result["ready"] is False and result["code"] == "model_missing"
    ollama_running(net, ["gemma4:12b"])
    assert api.get("/api/ai/ready").json()["ready"] is True


def test_ollama_status_when_not_installed(api: TestClient) -> None:
    status = api.get("/api/ai/ollama").json()
    assert status["running"] is False
    assert status["download_page"] == "https://ollama.com/download"
    assert [m["name"] for m in status["recommended"]] == ["gemma4:12b", "gemma4:e4b"]


def test_ollama_status_marks_installed_models(api: TestClient, net: FakeNet) -> None:
    ollama_running(net, ["gemma4:e4b"])
    status = api.get("/api/ai/ollama").json()
    assert status["running"] is True and status["version"] == "0.40.15"
    installed = {m["name"]: m["installed"] for m in status["recommended"]}
    assert installed == {"gemma4:12b": False, "gemma4:e4b": True}


def test_pull_downloads_with_progress(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    net.on(
        "POST",
        f"{OLLAMA}/api/pull",
        [
            {"status": "pulling manifest"},
            {"status": "pulling a", "digest": "a", "total": 6_000_000_000, "completed": 3_000_000_000},
            {"status": "pulling b", "digest": "b", "total": 2_000_000_000, "completed": 2_000_000_000},
            {"status": "pulling a", "digest": "a", "total": 6_000_000_000, "completed": 6_000_000_000},
            {"status": "success"},
        ],
    )
    job = api.post("/api/ai/ollama/pull", json={"model": "gemma4:12b"}).json()
    done = wait_job(svc, job["id"], "done", "failed")
    assert done["status"] == "done", done
    assert done["total"] == 8_000_000_000 and done["progress"] == 8_000_000_000
    assert done["message"] == "gemma4:12b is downloaded and ready"
    assert net.requests[-1]["json"] == {"model": "gemma4:12b", "stream": True}


class RecordingContext:
    """Stands in for a job's JobContext and remembers every progress report."""

    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.reports: list[tuple[int, int | None]] = []

    def progress(self, done: int, total: int | None = None, message: str | None = None) -> None:
        self.reports.append((done, total))

    def check(self) -> None:
        pass


def test_pull_bar_never_jumps_back_when_size_is_known(net: FakeNet) -> None:
    # Ollama announces the small layer first, then the big one.
    net.on(
        "POST",
        f"{OLLAMA}/api/pull",
        [
            {"status": "pulling a", "digest": "a", "total": GB // 5, "completed": GB // 10},
            {"status": "pulling a", "digest": "a", "total": GB // 5, "completed": GB // 5},
            {"status": "pulling b", "digest": "b", "total": 7 * GB, "completed": GB},
            {"status": "verifying sha256 digest"},
            {"status": "success"},
        ],
    )
    ctx = RecordingContext({"model": "gemma4:12b", "expected_bytes": 8 * GB})
    make_pull_handler(net.client())(ctx)  # type: ignore[arg-type]
    shares = [done / total for done, total in ctx.reports if total]
    assert shares == sorted(shares), ctx.reports  # always moving forward
    assert ctx.reports[1] == (GB // 10, 8 * GB)  # first layer measured against the full size


def test_new_download_replaces_interrupted_one(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    net.on("POST", f"{OLLAMA}/api/pull", [{"status": "success"}])
    old_id = svc.jobs.create("ollama_pull", "Download gemma4:12b", {"model": "gemma4:12b"})
    svc.jobs.update(old_id, status="interrupted")
    new_job = api.post("/api/ai/ollama/pull", json={"model": "gemma4:12b"}).json()
    assert new_job["id"] != old_id
    assert new_job["params"]["expected_bytes"] == 8 * GB
    assert svc.jobs.get(old_id)["status"] == "cancelled"  # type: ignore[index]
    assert wait_job(svc, new_job["id"], "done")["status"] == "done"


def test_pressing_download_twice_shows_the_running_job(
    api: TestClient, svc: AppServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    running_id = svc.jobs.create("ollama_pull", "Download gemma4:12b", {"model": "gemma4:12b"})
    svc.jobs.update(running_id, status="running")
    # The half-done download has used up the space; that must not block this.
    monkeypatch.setattr("app.api.ai.free_disk_bytes", lambda _folder: 1 * GB)
    assert api.post("/api/ai/ollama/pull", json={"model": "gemma4:12b"}).json()["id"] == running_id


def test_pull_refuses_when_disk_is_too_full(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.ai.free_disk_bytes", lambda _folder: 3 * GB)
    response = api.post("/api/ai/ollama/pull", json={"model": "gemma4:12b"})
    assert response.status_code == 400
    assert response.json()["code"] == "no_space"
    assert "3.0 GB is free" in response.json()["detail"]


def test_pull_reports_ollama_errors(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    net.on("POST", f"{OLLAMA}/api/pull", [{"error": "pull model manifest: file does not exist"}])
    job = api.post("/api/ai/ollama/pull", json={"model": "nope:1b"}).json()
    failed = wait_job(svc, job["id"], "failed")
    assert "file does not exist" in failed["error"]


def test_pull_without_ollama_suggests_command(api: TestClient, svc: AppServices) -> None:
    job = api.post("/api/ai/ollama/pull", json={"model": "gemma4:12b"}).json()
    failed = wait_job(svc, job["id"], "failed")
    assert "ollama pull gemma4:12b" in failed["error"]


def test_setup_done_flag(api: TestClient) -> None:
    assert api.post("/api/ai/setup-done", json={"done": True}).json()["setup_done"] is True
