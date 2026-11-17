"""AIService: the single door the rest of the app uses to reach the AI.

It knows which provider and model the user picked (saved in settings),
fetches the API key from Credential Manager, and builds the provider.
Switching provider takes effect on the next call; no restart needed.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.base import AIError, Message, Provider
from app.ai.http import HttpClient
from app.ai.json_tools import chat_json
from app.ai.registry import (
    DEFAULT_PROVIDER,
    PROVIDER_CLASSES,
    make_provider,
    provider_info,
    suggest_model,
)
from app.ai.secrets import KeyStore, mask
from app.db.settings_repo import SettingsRepo

T = TypeVar("T", bound=BaseModel)

# Setting names in the database.
CURRENT = "ai.provider"
MODELS = "ai.models"  # {provider id: model name}
BASE_URLS = "ai.base_urls"  # {provider id: base url}
SETUP_DONE = "setup_done"


class AIService:
    def __init__(self, settings: SettingsRepo, keys: KeyStore, http: HttpClient | None = None) -> None:
        self.settings = settings
        self.keys = keys
        self.http = http or HttpClient()

    # ---------- what the user picked ----------

    def current_id(self) -> str:
        return str(self.settings.get(CURRENT, DEFAULT_PROVIDER))

    def set_current(self, provider_id: str) -> None:
        provider_info(provider_id)  # unknown ids raise
        self.settings.set(CURRENT, provider_id)

    def model_for(self, provider_id: str) -> str:
        models: dict[str, str] = self.settings.get(MODELS, {})
        return models.get(provider_id) or provider_info(provider_id).default_model

    def set_model(self, provider_id: str, model: str) -> None:
        provider_info(provider_id)
        models: dict[str, str] = self.settings.get(MODELS, {})
        models[provider_id] = model.strip()
        self.settings.set(MODELS, models)

    def base_url_for(self, provider_id: str) -> str:
        urls: dict[str, str] = self.settings.get(BASE_URLS, {})
        return urls.get(provider_id) or provider_info(provider_id).default_base_url

    def set_base_url(self, provider_id: str, url: str) -> None:
        info = provider_info(provider_id)
        if info.kind != "local":
            raise AIError("Only local providers have an editable address.")
        urls: dict[str, str] = self.settings.get(BASE_URLS, {})
        urls[provider_id] = url.strip().rstrip("/")
        self.settings.set(BASE_URLS, urls)

    # ---------- API keys (Credential Manager) ----------

    def save_key(self, provider_id: str, key: str) -> None:
        if not provider_info(provider_id).needs_key:
            raise AIError("This provider doesn't use an API key.")
        key = key.strip()
        if not key:
            raise AIError("The API key is empty.")
        self.keys.set(provider_id, key)

    def remove_key(self, provider_id: str) -> None:
        self.keys.delete(provider_id)

    # ---------- building providers ----------

    def provider(self, provider_id: str | None = None) -> Provider:
        pid = provider_id or self.current_id()
        return make_provider(
            pid,
            self.http,
            model=self.model_for(pid),
            base_url=self.base_url_for(pid),
            api_key=self.keys.get(pid) or "",
        )

    def chat(self, messages: list[Message], temperature: float = 0.2) -> str:
        return self.provider().chat(messages, temperature=temperature)

    def chat_json(self, messages: list[Message], model_cls: type[T]) -> T:
        return chat_json(self.provider(), messages, model_cls)

    def current_label(self) -> str:
        """e.g. 'Ollama · gemma4:12b', saved with every AI result."""
        pid = self.current_id()
        return f"{provider_info(pid).label} · {self.model_for(pid)}"

    def is_cloud(self) -> bool:
        return provider_info(self.current_id()).kind == "cloud"

    # ---------- for the Settings screen ----------

    def list_models(self, provider_id: str) -> list[str]:
        models = self.provider(provider_id).list_models()
        # First time a key works: pre-pick a sensible model.
        if models and not self.settings.get(MODELS, {}).get(provider_id) and not provider_info(provider_id).default_model:
            self.set_model(provider_id, suggest_model(models))
        return models

    def test_connection(self, provider_id: str | None = None) -> str:
        return self.provider(provider_id).test_connection()

    def overview(self) -> dict[str, Any]:
        current = self.current_id()
        providers = []
        for cls in PROVIDER_CLASSES:
            info = cls.info
            key = self.keys.get(info.id) if info.needs_key else None
            providers.append(
                {
                    "id": info.id,
                    "label": info.label,
                    "kind": info.kind,
                    "needs_key": info.needs_key,
                    "key_saved": bool(key),
                    "key_hint": mask(key) if key else None,
                    "key_url": info.key_url,
                    "model": self.model_for(info.id),
                    "base_url": self.base_url_for(info.id),
                    "default_base_url": info.default_base_url,
                }
            )
        return {
            "current": current,
            "current_kind": provider_info(current).kind,
            "current_label": self.current_label(),
            "setup_done": bool(self.settings.get(SETUP_DONE, False)),
            "providers": providers,
        }

    def check_ready(self) -> None:
        """Raise AIError (with a code the UI understands) if AI jobs can't run yet."""
        pid = self.current_id()
        info = provider_info(pid)
        if info.needs_key and not self.keys.get(pid):
            raise AIError(f"Add your {info.label} API key in Settings first.", "missing_key")
        if not self.model_for(pid):
            raise AIError(f"Pick a {info.label} model in Settings first.", "missing_model")
        if pid == "ollama":
            installed = self.provider(pid).list_models()  # raises if Ollama isn't running
            if self.model_for(pid) not in installed:
                raise AIError(
                    f"The model {self.model_for(pid)} isn't downloaded yet.", "model_missing"
                )
