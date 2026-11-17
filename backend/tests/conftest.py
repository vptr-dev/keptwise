"""Shared test setup.

Every test gets its own empty data folder, so tests never read or change
the real one in %APPDATA%.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.secrets import MemoryKeyStore
from app.api.session import TOKEN_HEADER
from app.main import create_app
from app.paths import DATA_DIR_ENV
from app.services import AppServices, build_services
from tests.fakes import FakeNet

TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return data_dir


@pytest.fixture
def net() -> FakeNet:
    """The fake internet every test's AI calls go to."""
    return FakeNet()


@pytest.fixture
def keys() -> MemoryKeyStore:
    return MemoryKeyStore()


@pytest.fixture
def svc(isolated_data_dir: Path, net: FakeNet, keys: MemoryKeyStore) -> Iterator[AppServices]:
    services = build_services(isolated_data_dir, keys=keys, http=net.client())
    yield services
    services.shutdown()


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A fake built frontend with just an index.html."""
    folder = tmp_path / "static"
    folder.mkdir()
    (folder / "index.html").write_text("<h1>Fake frontend</h1>", encoding="utf-8")
    return folder


@pytest.fixture
def api(svc: AppServices, static_dir: Path) -> TestClient:
    """A test client that already carries the session token."""
    app = create_app(session_token=TOKEN, static_dir=static_dir, app_services=svc)
    return TestClient(app, headers={TOKEN_HEADER: TOKEN})
