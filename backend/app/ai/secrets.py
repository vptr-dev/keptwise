"""API keys, kept in Windows Credential Manager (never in files or the database).

The `keyring` package talks to Credential Manager on Windows. You can see the
saved keys in Control Panel > Credential Manager > Windows Credentials,
listed under "Keptwise". Keys saved by older versions (under
"SavesKnowledge") are moved to the new name the first time they are read.
"""

from __future__ import annotations

from typing import Protocol

SERVICE_NAME = "Keptwise"
OLD_SERVICE_NAME = "SavesKnowledge"  # the name older versions used


class KeyStore(Protocol):
    def get(self, provider_id: str) -> str | None: ...
    def set(self, provider_id: str, key: str) -> None: ...
    def delete(self, provider_id: str) -> None: ...


class KeyringStore:
    """The real store: Windows Credential Manager via keyring."""

    def get(self, provider_id: str) -> str | None:
        import keyring

        key = keyring.get_password(SERVICE_NAME, provider_id)
        if key is None:
            key = keyring.get_password(OLD_SERVICE_NAME, provider_id)
            if key is not None:  # saved by an older version: move it to the new name
                keyring.set_password(SERVICE_NAME, provider_id, key)
                self._delete(OLD_SERVICE_NAME, provider_id)
        return key

    def set(self, provider_id: str, key: str) -> None:
        import keyring

        keyring.set_password(SERVICE_NAME, provider_id, key)

    def delete(self, provider_id: str) -> None:
        self._delete(SERVICE_NAME, provider_id)
        self._delete(OLD_SERVICE_NAME, provider_id)

    @staticmethod
    def _delete(service: str, provider_id: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(service, provider_id)
        except PasswordDeleteError:
            pass  # wasn't saved; nothing to delete


class MemoryKeyStore:
    """Keeps keys in memory only. Used by tests."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def get(self, provider_id: str) -> str | None:
        return self._keys.get(provider_id)

    def set(self, provider_id: str, key: str) -> None:
        self._keys[provider_id] = key

    def delete(self, provider_id: str) -> None:
        self._keys.pop(provider_id, None)


def mask(key: str) -> str:
    """Show only the end of a key, e.g. '••••3f9a'."""
    return "••••" + key[-4:] if len(key) > 4 else "••••"
