"""Google Gemini (cloud, needs the user's API key)."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIError, Message, Provider, ProviderInfo, first_system_and_rest
from app.ai.http import HttpError


class GeminiProvider(Provider):
    info = ProviderInfo(
        id="gemini",
        label="Gemini",
        kind="cloud",
        needs_key=True,
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        key_url="https://aistudio.google.com/apikey",
    )

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key}

    def chat(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        self.require_key()
        self.require_model()
        system, rest = first_system_and_rest(messages)
        config: dict[str, Any] = {"temperature": temperature}
        if json_schema is not None:
            config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {
            "contents": [
                {
                    # Gemini calls the assistant "model".
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}]
                    + [{"inline_data": {"mime_type": "image/jpeg", "data": data}} for data in m.get("images") or []],
                }
                for m in rest
            ],
            "generationConfig": config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        model = self.model.removeprefix("models/")
        try:
            data = self.http.post_json(
                f"{self.base_url}/models/{model}:generateContent",
                payload,
                self._headers(),
                timeout=300,
            )
        except HttpError as error:
            raise self.friendly(error) from error
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as error:
            raise AIError("Gemini sent an empty answer (it may have been blocked).") from error
        return "".join(part.get("text", "") for part in parts)

    def list_models(self) -> list[str]:
        self.require_key()
        try:
            data = self.http.get_json(f"{self.base_url}/models?pageSize=200", self._headers())
        except HttpError as error:
            raise self.friendly(error) from error
        return sorted(
            model["name"].removeprefix("models/")
            for model in data.get("models", [])
            if "generateContent" in model.get("supportedGenerationMethods", [])
        )
