"""Tests for the backend app: health, session token, hello, and pages."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.api.session import SESSION_COOKIE, TOKEN_HEADER
from app.main import create_app

TOKEN = "test-token-123"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A fake built frontend with just an index.html."""
    (tmp_path / "index.html").write_text("<h1>Fake frontend</h1>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(static_dir: Path) -> TestClient:
    return TestClient(create_app(session_token=TOKEN, static_dir=static_dir))


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_hello_is_refused_without_token(client: TestClient) -> None:
    assert client.get("/api/hello").status_code == 401


def test_hello_is_refused_with_wrong_token(client: TestClient) -> None:
    response = client.get("/api/hello", headers={TOKEN_HEADER: "wrong"})
    assert response.status_code == 401


def test_hello_works_with_token_header(client: TestClient) -> None:
    response = client.get("/api/hello", headers={TOKEN_HEADER: TOKEN})
    assert response.status_code == 200
    assert response.json()["message"] == "Hello from Keptwise!"


def test_session_start_sets_cookie_and_goes_home(client: TestClient) -> None:
    response = client.get(f"/session/start?token={TOKEN}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    set_cookie = response.headers["set-cookie"].lower()
    assert SESSION_COOKIE in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    # The test client keeps the cookie, like the app window does.
    assert client.get("/api/hello").status_code == 200


def test_session_start_rejects_wrong_token(client: TestClient) -> None:
    response = client.get("/session/start?token=wrong", follow_redirects=False)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert client.get("/api/hello").status_code == 401


def test_serves_the_built_frontend(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Fake frontend" in response.text


def test_shows_help_page_when_frontend_not_built(tmp_path: Path) -> None:
    app = create_app(session_token=TOKEN, static_dir=tmp_path / "missing")
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "haven't been built yet" in response.text
