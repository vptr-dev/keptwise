"""The one interface every AI provider follows.

The rest of the app only talks to this interface (through AIService),
never to a specific provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.ai.http import HttpClient, HttpError

# A chat message: {"role": "system" | "user" | "assistant", "content": "..."}
# A user message may also carry pictures for models that can see:
# "images": ["<base64 JPEG>", ...]. Each provider turns that into its own shape.
Message = dict[str, Any]


def without_images(messages: list[Message]) -> list[Message]:
    """The same conversation with the pictures left out."""
    return [{key: value for key, value in m.items() if key != "images"} for m in messages]


def has_images(messages: list[Message]) -> bool:
    return any(m.get("images") for m in messages)


class AIError(Exception):
    """Something went wrong with the AI. The message is shown to the user."""

    def __init__(self, message: str, code: str = "ai_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    kind: str  # "local" or "cloud"
    needs_key: bool
    default_base_url: str
    default_model: str = ""
    key_url: str = ""  # where the user creates an API key
    supports_schema: bool = False  # can force answers to match a JSON schema


class Provider(ABC):
    info: ProviderInfo

    def __init__(self, http: HttpClient, model: str, base_url: str = "", api_key: str = "") -> None:
        self.http = http
        self.model = model
        self.base_url = (base_url or self.info.default_base_url).rstrip("/")
        self.api_key = api_key

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Send the conversation, return the reply text.

        json_schema: ask for an answer that is JSON matching this schema.
        """

    @abstractmethod
    def list_models(self) -> list[str]:
        """Names of the models the user can pick."""

    def test_connection(self) -> str:
        """Check we can reach the provider. Returns a short success message."""
        models = self.list_models()
        if not self.model:
            return f"Connected. {len(models)} models available; pick one."
        reply = self.chat([{"role": "user", "content": "Reply with just the word: ready"}])
        return f"Connected to {self.info.label} ({self.model}). It replied: {reply.strip()[:60]}"

    # ---------- helpers for the provider classes ----------

    def require_key(self) -> None:
        if self.info.needs_key and not self.api_key:
            raise AIError(f"Add your {self.info.label} API key in Settings first.", "missing_key")

    def require_model(self) -> None:
        if not self.model:
            raise AIError(f"Pick a {self.info.label} model in Settings first.", "missing_model")

    def friendly(self, error: HttpError) -> AIError:
        """Turn an HTTP problem into a message a beginner can act on."""
        label = self.info.label
        if error.status is None:
            if self.info.kind == "local":
                return AIError(
                    f"Couldn't reach {label} at {self.base_url}. Is it installed and running?",
                    "unreachable",
                )
            return AIError(f"Couldn't reach {label}. Check your internet connection.", "unreachable")
        if error.status in (401, 403):
            return AIError(f"{label} refused the API key. Check it in Settings.", "bad_key")
        if error.status == 404:
            return AIError(
                f"{label} doesn't know the model '{self.model}'. Pick another in Settings.",
                "model_missing",
            )
        if error.status == 429:
            return AIError(
                f"{label} says you've hit a rate limit or run out of credits. Try again later.",
                "rate_limited",
            )
        detail = error.body.strip()[:200]
        return AIError(f"{label} returned an error ({error.status}). {detail}", "provider_error")


def first_system_and_rest(messages: list[Message]) -> tuple[str, list[Message]]:
    """Split out the system message (some APIs want it separately)."""
    system = "\n\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    rest = [m for m in messages if m["role"] != "system"]
    return system, rest
