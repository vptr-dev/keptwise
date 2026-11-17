"""Anthropic Claude (cloud, needs the user's API key)."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIError, Message, Provider, ProviderInfo, first_system_and_rest
from app.ai.http import HttpError

API_VERSION = "2023-06-01"
# Current Claude models think before answering, and that thinking counts
# toward this limit, so leave plenty of room.
MAX_TOKENS = 16000


class AnthropicProvider(Provider):
    info = ProviderInfo(
        id="anthropic",
        label="Claude",
        kind="cloud",
        needs_key=True,
        default_base_url="https://api.anthropic.com",
        default_model="claude-haiku-5-5",
        key_url="https://console.anthropic.com/settings/keys",
    )

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": API_VERSION}

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
        # No "temperature": current Claude models reject it (HTTP 400).
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [_with_pictures(m) for m in rest],
        }
        if system:
            payload["system"] = system
        try:
            data = self.http.post_json(
                f"{self.base_url}/v1/messages", payload, self._headers(), timeout=300
            )
        except HttpError as error:
            raise self.friendly(error) from error
        if data.get("stop_reason") == "refusal":
            raise AIError("Claude declined to answer this one. Try another item or provider.", "refused")
        # Skip "thinking" blocks; only "text" blocks are the answer.
        texts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        if not texts:
            raise AIError("Claude sent an empty answer.")
        return "".join(texts)

    def list_models(self) -> list[str]:  # noqa: D102
        self.require_key()
        try:
            data = self.http.get_json(f"{self.base_url}/v1/models?limit=100", self._headers())
        except HttpError as error:
            raise self.friendly(error) from error
        return sorted(model["id"] for model in data.get("data", []))


def _with_pictures(message: Message) -> dict[str, Any]:
    """Claude wants pictures as content blocks, before the text."""
    images = message.get("images") or []
    if not images:
        return {"role": message["role"], "content": message["content"]}
    blocks: list[dict[str, Any]] = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}} for data in images
    ]
    blocks.append({"type": "text", "text": message["content"]})
    return {"role": message["role"], "content": blocks}
