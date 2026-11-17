"""Checks GitHub for a newer release of Keptwise.

Privacy: one plain request to GitHub's public releases page for this app,
at most once a day, with a generic User-Agent and nothing about the user.
It can be switched off in Settings -> About and updates. Nothing is
downloaded until the user presses "Update now" (app/updater.py).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app import __version__
from app.ai.http import HttpClient, HttpError
from app.db.settings_repo import SettingsRepo

REPO = "vptr-dev/keptwise"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SETTINGS_KEY = "updates"
CHECK_EVERY = timedelta(days=1)
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Keptwise-update-check"}


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """'v1.2.3' or '1.2.3.dev0' -> (1, 2, 3). None if it isn't a version."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def is_newer(latest: str | None, current: str) -> bool:
    new, now = parse_version(latest), parse_version(current)
    if new is None or now is None:
        return False
    if new != now:
        return new > now
    # Same numbers: a finished release is newer than a ".dev" build of it.
    return ".dev" in current and ".dev" not in (latest or "")


def _now() -> datetime:
    return datetime.now(UTC)


class UpdateChecker:
    def __init__(self, settings: SettingsRepo, http: HttpClient, current: str = __version__) -> None:
        self._settings = settings
        self._http = http
        self.current = current

    def _state(self) -> dict[str, Any]:
        state = self._settings.get(SETTINGS_KEY, {}) or {}
        return state if isinstance(state, dict) else {}

    def enabled(self) -> bool:
        return bool(self._state().get("enabled", True))

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self._settings.set(SETTINGS_KEY, self._state() | {"enabled": enabled})
        return self.status()

    def status(self) -> dict[str, Any]:
        state = self._state()
        latest = state.get("latest")
        return {
            "enabled": bool(state.get("enabled", True)),
            "current": self.current,
            "latest": latest,
            "update_available": is_newer(latest, self.current),
            "url": state.get("url") or RELEASES_PAGE,
            "checked_at": state.get("checked_at"),
            "error": state.get("error"),
        }

    def check(self, force: bool = False) -> dict[str, Any]:
        """Ask GitHub, unless switched off or already asked today (force: the "Check now" button)."""
        state = self._state()
        if not state.get("enabled", True):
            return self.status()
        checked = state.get("checked_at")
        if not force and checked:
            try:
                if _now() - datetime.fromisoformat(checked) < CHECK_EVERY:
                    return self.status()
            except ValueError:
                pass
        state["checked_at"] = _now().isoformat(timespec="seconds")
        try:
            release = self._http.get_json(LATEST_URL, HEADERS, timeout=10)
            tag = release.get("tag_name") if isinstance(release, dict) else None
            if not parse_version(tag):
                raise HttpError("GitHub's answer had no version in it.")
            state.update(latest=str(tag).lstrip("v"), url=release.get("html_url") or RELEASES_PAGE, error=None)
        except (HttpError, ValueError) as error:
            # 404: no release yet, or the project page isn't public.
            state["error"] = (
                "No release could be found on GitHub (the project page may not be public yet)."
                if getattr(error, "status", None) == 404
                else "Couldn't reach GitHub to check for updates."
            )
        self._settings.set(SETTINGS_KEY, state)
        return self.status()
