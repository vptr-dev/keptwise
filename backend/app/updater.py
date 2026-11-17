"""Update Keptwise from inside the app, with one click (or "Update Keptwise"
in the command centre).

1. Read the newest release on GitHub and find Keptwise-Setup.exe in it.
2. Download it to %TEMP%\\Keptwise-update, then check its size and the
   SHA-256 checksum GitHub publishes for it. A file that doesn't match is
   deleted and never run.
3. Close the app; a hidden helper waits for it to be fully closed, then
   starts the installer silently. The installer deletes the
   old program files first (nothing outdated is left behind), installs into
   the same folder, keeps everything in %APPDATA%\\Keptwise, and opens the new
   version (/RELAUNCH, see packaging/Keptwise.iss).
4. The new version upgrades the database on its first start, after copying it
   to the backups folder, and deletes the downloaded installer.

Only the installed app can update itself. Running from source, pull the code.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.updates import HEADERS, LATEST_URL, is_newer, parse_version

ASSET = "Keptwise-Setup.exe"
# Silent, for this Windows user, close the running app, then open the new one.
INSTALLER_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/CLOSEAPPLICATIONS", "/RELAUNCH"]
CHUNK = 256 * 1024


class UpdateError(Exception):
    """Something the user should read (shown as the job's error)."""


@dataclass
class Installer:
    version: str
    url: str
    size: int
    sha256: str | None


def update_folder() -> Path:
    return Path(tempfile.gettempdir()) / "Keptwise-update"


def can_update_itself() -> bool:
    """Only the installed app (a frozen build) can run its own installer."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def find_installer(release: Any) -> Installer:
    """The installer in GitHub's answer for the newest release."""
    if not isinstance(release, dict) or not parse_version(release.get("tag_name")):
        raise UpdateError("GitHub's answer had no version in it.")
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == ASSET and asset.get("browser_download_url"):
            digest = str(asset.get("digest") or "")
            return Installer(
                version=str(release["tag_name"]).lstrip("v"),
                url=str(asset["browser_download_url"]),
                size=int(asset.get("size") or 0),
                sha256=digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else None,
            )
    raise UpdateError("The newest release has no installer yet. Try again in a few minutes.")


Opener = Callable[[urllib.request.Request], Any]


def download(
    installer: Installer,
    folder: Path,
    progress: Callable[[int, int], None],
    check: Callable[[], None] = lambda: None,
    opener: Opener = lambda request: urllib.request.urlopen(request, timeout=60),  # noqa: S310 - fixed https address
) -> Path:
    """Download the installer and check it. Returns where it was saved."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Keptwise-Setup-{installer.version}.exe"
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    done = 0
    request = urllib.request.Request(installer.url, headers={"User-Agent": HEADERS["User-Agent"]})
    try:
        with opener(request) as response, open(partial, "wb") as out:
            total = installer.size or int(response.headers.get("Content-Length") or 0)
            while chunk := response.read(CHUNK):
                check()
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(done, total)
        if installer.size and done != installer.size:
            raise UpdateError("The download stopped part way. Try again.")
        if installer.sha256 and digest.hexdigest() != installer.sha256:
            raise UpdateError("The downloaded installer didn't match GitHub's checksum, so it wasn't run. Try again.")
        partial.replace(target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def installer_command(path: Path, app_pid: int) -> list[str]:
    """A hidden PowerShell that waits until this app has fully closed, then
    runs the installer. (Starting the installer while the window is still
    closing made the two get in each other's way.)"""
    args = ",".join(f"'{arg}'" for arg in INSTALLER_ARGS)
    script = (
        f"Wait-Process -Id {app_pid} -Timeout 60 -ErrorAction SilentlyContinue; "
        f"Start-Process -FilePath '{str(path).replace(chr(39), chr(39) * 2)}' -ArgumentList {args}"
    )
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script]


def helper_flags() -> int:
    """How the helper is started: its own process group with a hidden console.
    Not DETACHED_PROCESS: PowerShell without a console quits at once, silently,
    and the installer never runs."""
    if sys.platform != "win32":
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]


def start_installer(path: Path, popen: Callable[..., Any] = subprocess.Popen) -> None:
    """Start the hidden helper on its own, so it keeps going after the app closes."""
    flags = helper_flags()
    popen(installer_command(path, os.getpid()), creationflags=flags, close_fds=True, cwd=str(path.parent))


def clean_downloads(folder: Path | None = None) -> None:
    """Delete installers downloaded for earlier updates (the update is done)."""
    shutil.rmtree(folder or update_folder(), ignore_errors=True)


def make_update_handler(
    get_json: Callable[[str, dict[str, str]], Any],
    current: str,
    quit_app: Callable[[], Callable[[], None] | None],
    folder: Callable[[], Path] = update_folder,
    opener: Opener | None = None,
    starter: Callable[[Path], None] = start_installer,
) -> Callable[[Any], dict[str, Any]]:
    """The "update" job: download, check, start the installer, close the app."""

    def run(ctx: Any) -> dict[str, Any]:
        ctx.progress(0, 0, "Looking for the newest version", force=True)
        try:
            release = get_json(LATEST_URL, HEADERS)
        except Exception as error:  # noqa: BLE001 - offline, GitHub down, ...
            raise UpdateError("Couldn't reach GitHub. Check your internet connection and try again.") from error
        installer = find_installer(release)
        if not is_newer(installer.version, current):
            return {"message": f"You already have the newest version ({current}).", "updated": False}
        mb = installer.size / 1_000_000 if installer.size else 0

        def report(done: int, total: int) -> None:
            ctx.progress(done, total, f"Downloading version {installer.version}" + (f" ({mb:.0f} MB)" if mb else ""))

        kwargs = {"opener": opener} if opener else {}
        try:
            path = download(installer, folder(), report, ctx.check, **kwargs)
        except OSError as error:  # the connection dropped, the disk is full, ...
            raise UpdateError("The update couldn't be downloaded. Check your internet connection and try again.") from error
        ctx.progress(1, 1, f"Installing version {installer.version}. Keptwise will close and open again.", force=True)
        starter(path)
        close = quit_app()
        if close:
            threading.Timer(1.0, close).start()  # let the window show the last message first
        return {"message": f"Installing version {installer.version}…", "updated": True, "version": installer.version}

    return run
