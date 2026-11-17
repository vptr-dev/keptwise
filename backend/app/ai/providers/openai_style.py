"""Providers that speak the OpenAI chat API: OpenAI, OpenRouter, LM Studio."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIError, Message, Provider, ProviderInfo
from app.ai.http import HttpError


class OpenAIStyleProvider(Provider):
    """Shared code for every OpenAI-compatible API."""

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def chat(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        self.require_key()
        self.require_model()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_with_pictures(m) for m in messages],
            "temperature": temperature,
        }
        if json_schema is not None:
            # Ask for JSON. The schema itself is in the prompt (see json_tools).
            payload["response_format"] = {"type": "json_object"}
        try:
            data = self._post_chat(payload)
        except HttpError as error:
            raise self.friendly(error) from error
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as error:
            raise AIError(f"{self.info.label} sent an answer the app didn't understand.") from error

    def _post_chat(self, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}/chat/completions"
        try:
            return self.http.post_json(url, payload, self._headers(), timeout=300)
        except HttpError as error:
            # Some newer models only accept their default temperature.
            # If that's the complaint, ask again without it.
            if error.status == 400 and "temperature" in error.body:
                without = {k: v for k, v in payload.items() if k != "temperature"}
                return self.http.post_json(url, without, self._headers(), timeout=300)
            raise

    def list_models(self) -> list[str]:
        self.require_key()
        try:
            data = self.http.get_json(f"{self.base_url}/models", self._headers())
        except HttpError as error:
            raise self.friendly(error) from error
        return sorted(model["id"] for model in data.get("data", []))


class OpenAIProvider(OpenAIStyleProvider):
    info = ProviderInfo(
        id="openai",
        label="OpenAI",
        kind="cloud",
        needs_key=True,
        default_base_url="https://api.openai.com/v1",
        key_url="https://platform.openai.com/api-keys",
    )


class OpenRouterProvider(OpenAIStyleProvider):
    info = ProviderInfo(
        id="openrouter",
        label="OpenRouter",
        kind="cloud",
        needs_key=True,
        default_base_url="https://openrouter.ai/api/v1",
        key_url="https://openrouter.ai/settings/keys",
    )


class LMStudioProvider(OpenAIStyleProvider):
    info = ProviderInfo(
        id="lmstudio",
        label="LM Studio",
        kind="local",
        needs_key=False,
        default_base_url="http://localhost:1234/v1",
    )


def _with_pictures(message: Message) -> dict[str, Any]:
    """OpenAI-style APIs want pictures as image_url parts with the data inline."""
    images = message.get("images") or []
    if not images:
        return {"role": message["role"], "content": message["content"]}
    parts: list[dict[str, Any]] = [{"type": "text", "text": message["content"]}]
    parts += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}} for data in images]
    return {"role": message["role"], "content": parts}
