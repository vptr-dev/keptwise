"""Ollama: free AI models that run on this computer (http://localhost:11434)."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIError, Message, Provider, ProviderInfo
from app.ai.http import HttpError


NOT_DOWNLOADED = "The model {model} isn't downloaded yet. Press its Download button."


def is_cloud_model(name: str) -> bool:
    """Ollama's cloud models have tags like 'gpt-oss:120b-cloud'."""
    tag = name.rpartition(":")[2] if ":" in name else ""
    return tag == "cloud" or tag.endswith("-cloud")


class OllamaProvider(Provider):
    info = ProviderInfo(
        id="ollama",
        label="Ollama",
        kind="local",
        needs_key=False,
        default_base_url="http://localhost:11434",
        default_model="gemma4:12b",
        supports_schema=True,
    )

    def chat(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        self.require_model()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
            # Models like gemma4 "think" before answering by default. That makes
            # each answer 2-3x slower and isn't needed for notes and sorting.
            "think": False,
        }
        if json_schema and not is_cloud_model(self.model):
            # Ollama forces the answer to match the schema. Its cloud models
            # don't support this, so for them we rely on the prompt alone.
            payload["format"] = json_schema
        try:
            data = self._post_chat(payload)
        except HttpError as error:
            raise self._friendly(error) from error
        if isinstance(data, dict) and data.get("error"):
            raise AIError(f"Ollama: {data['error']}")
        return str(data["message"]["content"])

    def _post_chat(self, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}/api/chat"
        try:
            return self.http.post_json(url, payload, timeout=600)
        except HttpError as error:
            # A model (or an older Ollama) that refuses the "think" setting:
            # ask again without it.
            if error.status == 400 and "think" in error.body:
                without = {k: v for k, v in payload.items() if k != "think"}
                return self.http.post_json(url, without, timeout=600)
            raise

    def list_models(self) -> list[str]:
        try:
            data = self.http.get_json(f"{self.base_url}/api/tags", timeout=5)
        except HttpError as error:
            raise self._friendly(error) from error
        return sorted(model["name"] for model in data.get("models", []))

    def version(self) -> str:
        try:
            return str(self.http.get_json(f"{self.base_url}/api/version", timeout=3)["version"])
        except HttpError as error:
            raise self._friendly(error) from error

    def test_connection(self) -> str:
        installed = self.list_models()
        if self.model and self.model not in installed:
            raise AIError(NOT_DOWNLOADED.format(model=self.model), "model_missing")
        return super().test_connection()

    def _friendly(self, error: HttpError) -> AIError:
        # Ollama answers 404 when the model hasn't been downloaded.
        if error.status == 404:
            return AIError(NOT_DOWNLOADED.format(model=self.model), "model_missing")
        return self.friendly(error)
