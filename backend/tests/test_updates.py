"""Tests for the GitHub update check and its off switch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import updates
from app.ai.http import HttpError
from app.db.connection import Database
from app.db.settings_repo import SettingsRepo
from app.updates import LATEST_URL, UpdateChecker, is_newer, parse_version
from tests.fakes import FakeNet


def test_versions_are_compared_by_number() -> None:
    assert parse_version("v1.10.0") == (1, 10, 0)
    assert parse_version("nightly") is None
    assert is_newer("0.2.0", "0.1.9")
    assert is_newer("1.10.0", "1.9.0")  # not compared as text
    assert not is_newer("0.1.0", "0.1.0")
    assert is_newer("0.1.0", "0.1.0.dev0")  # the release beats its own test build
    assert not is_newer("0.0.9", "0.1.0")
    assert not is_newer(None, "0.1.0")


@pytest.fixture
def checker(tmp_path, net: FakeNet) -> UpdateChecker:  # type: ignore[no-untyped-def]
    db = Database(tmp_path / "s.db")
    from app.db.migrations import migrate

    with db.connect() as conn:
        migrate(conn)
    return UpdateChecker(SettingsRepo(db), net.client(), current="0.1.0")


def test_a_newer_release_is_found_and_the_request_says_nothing_about_the_user(
    checker: UpdateChecker, net: FakeNet
) -> None:
    net.on("GET", LATEST_URL, {"tag_name": "v0.2.0", "html_url": "https://github.com/x/releases/tag/v0.2.0"})
    status = checker.check()
    assert status["update_available"] and status["latest"] == "0.2.0"
    assert status["url"].endswith("v0.2.0") and status["error"] is None
    assert net.requests[0]["headers"]["User-Agent"] == "Keptwise-update-check"
    assert net.requests[0]["json"] is None


def test_asks_at_most_once_a_day_unless_forced(checker: UpdateChecker, net: FakeNet,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    net.on("GET", LATEST_URL, {"tag_name": "v0.1.0"})
    checker.check()
    checker.check()
    assert len(net.requests) == 1
    checker.check(force=True)
    assert len(net.requests) == 2
    later = datetime.now(UTC) + timedelta(days=2)
    monkeypatch.setattr(updates, "_now", lambda: later)
    checker.check()
    assert len(net.requests) == 3


def test_switched_off_means_no_request(checker: UpdateChecker, net: FakeNet) -> None:
    checker.set_enabled(False)
    assert checker.check(force=True)["enabled"] is False
    assert net.requests == []


def test_a_private_or_missing_release_is_explained(checker: UpdateChecker, net: FakeNet) -> None:
    net.on("GET", LATEST_URL, HttpError("HTTP 404", status=404))
    assert checker.check()["error"] == "No release could be found on GitHub (the project page may not be public yet)."
    net.on("GET", LATEST_URL, HttpError("Couldn't connect"))
    status = checker.check(force=True)
    assert status["error"] == "Couldn't reach GitHub to check for updates."
    assert not status["update_available"]


def test_update_routes(api: TestClient, net: FakeNet) -> None:
    net.on("GET", LATEST_URL, {"tag_name": "v99.0.0"})
    assert api.get("/api/updates").json()["update_available"] is True
    assert api.put("/api/updates", json={"enabled": False}).json()["enabled"] is False
    assert api.post("/api/updates/check").json()["enabled"] is False
    assert len(net.requests) == 1
