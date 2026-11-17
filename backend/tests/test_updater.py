"""One-click update: find the installer, download and check it, run it, close the app."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.updater import (INSTALLER_ARGS, Installer, UpdateError, download, find_installer, helper_flags, installer_command,
                         make_update_handler)

SETUP = b"pretend installer" * 1000
SHA = hashlib.sha256(SETUP).hexdigest()


def release(tag: str = "v1.2.0", sha: str = SHA, size: int = len(SETUP)) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://x/notes.txt"},
            {"name": "Keptwise-Setup.exe", "size": size, "digest": f"sha256:{sha}",
             "browser_download_url": f"https://github.com/vptr-dev/keptwise/releases/download/{tag}/Keptwise-Setup.exe"},
        ],
    }


class Response(io.BytesIO):
    headers: dict[str, str] = {}

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Ctx:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def progress(self, done: int, total: int | None = None, message: str | None = None, force: bool = False) -> None:
        if message and (not self.messages or self.messages[-1] != message):
            self.messages.append(message)

    def check(self) -> None:
        pass


def test_finds_the_installer_and_its_checksum() -> None:
    found = find_installer(release())
    assert found == Installer("1.2.0", "https://github.com/vptr-dev/keptwise/releases/download/v1.2.0/Keptwise-Setup.exe", len(SETUP), SHA)
    with pytest.raises(UpdateError, match="no installer yet"):
        find_installer({"tag_name": "v1.2.0", "assets": []})


def test_a_download_is_kept_only_if_it_matches_githubs_checksum(tmp_path: Path) -> None:
    good = download(find_installer(release()), tmp_path, lambda d, t: None, opener=lambda r: Response(SETUP))
    assert good.read_bytes() == SETUP and good.name == "Keptwise-Setup-1.2.0.exe"

    tampered = find_installer(release(tag="v1.3.0"))
    with pytest.raises(UpdateError, match="checksum"):
        download(tampered, tmp_path, lambda d, t: None, opener=lambda r: Response(SETUP[:-1] + b"!"))
    with pytest.raises(UpdateError, match="part way"):
        download(tampered, tmp_path, lambda d, t: None, opener=lambda r: Response(SETUP[:100]))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Keptwise-Setup-1.2.0.exe"]  # nothing half-done is left


def test_the_update_job_downloads_runs_the_installer_and_closes_the_app(tmp_path: Path) -> None:
    started: list[Path] = []
    closed: list[bool] = []
    run = make_update_handler(
        lambda url, headers: release(),
        "1.0.0",
        lambda: lambda: closed.append(True),
        folder=lambda: tmp_path,
        opener=lambda r: Response(SETUP),
        starter=started.append,
    )
    ctx = Ctx()
    result = run(ctx)
    assert result["updated"] is True and result["version"] == "1.2.0"
    assert started == [tmp_path / "Keptwise-Setup-1.2.0.exe"]
    assert ctx.messages[-1].startswith("Installing version 1.2.0")
    assert "/RELAUNCH" in INSTALLER_ARGS and "/VERYSILENT" in INSTALLER_ARGS
    # Already up to date: nothing is downloaded or run.
    same = make_update_handler(lambda url, headers: release(tag="v1.0.0"), "1.0.0", lambda: None, folder=lambda: tmp_path,
                               starter=started.append)
    assert same(Ctx())["updated"] is False and len(started) == 1


def test_the_installer_waits_until_the_app_has_closed() -> None:
    command = installer_command(Path(r"C:\Temp\Keptwise-update\Keptwise-Setup-1.2.0.exe"), 4321)
    assert command[0] == "powershell.exe" and "Hidden" in command
    script = command[-1]
    assert script.startswith("Wait-Process -Id 4321")
    assert r"Start-Process -FilePath 'C:\Temp\Keptwise-update\Keptwise-Setup-1.2.0.exe'" in script
    assert "'/RELAUNCH'" in script and script.index("Wait-Process") < script.index("Start-Process")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows helper")
def test_the_helper_really_runs_its_script(tmp_path: Path) -> None:
    # Started the way the app starts it, PowerShell must actually run the script
    # (with DETACHED_PROCESS it quit at once and the installer never started).
    out = tmp_path / "ran.txt"
    command = installer_command(Path(r"C:\nothing-here.exe"), 1)
    command[-1] = f"'ran' | Out-File '{out}'"
    helper = subprocess.Popen(command, creationflags=helper_flags(), close_fds=True)
    assert helper.wait(60) == 0
    assert out.exists()


def test_offline_gives_a_plain_message(tmp_path: Path) -> None:
    def offline(url: str, headers: dict[str, str]) -> Any:
        raise OSError("no network")

    run = make_update_handler(offline, "1.0.0", lambda: None, folder=lambda: tmp_path)
    with pytest.raises(UpdateError, match="Couldn't reach GitHub"):
        run(Ctx())


def test_only_the_installed_app_can_update_itself(api: Any) -> None:
    response = api.post("/api/updates/install")
    assert response.status_code == 409 and "installed app" in response.json()["detail"]
    assert api.get("/api/updates").json()["can_install"] is False
