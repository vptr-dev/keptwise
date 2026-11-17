"""The list of AI providers the user can choose from."""

from __future__ import annotations

from app.ai.base import AIError, Provider, ProviderInfo
from app.ai.http import HttpClient
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_style import (
    LMStudioProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

# Order shown in Settings: local first, then cloud.
PROVIDER_CLASSES: list[type[Provider]] = [
    OllamaProvider,
    LMStudioProvider,
    AnthropicProvider,
    OpenAIProvider,
    GeminiProvider,
    OpenRouterProvider,
]

PROVIDERS: dict[str, type[Provider]] = {cls.info.id: cls for cls in PROVIDER_CLASSES}

DEFAULT_PROVIDER = "ollama"


def provider_info(provider_id: str) -> ProviderInfo:
    if provider_id not in PROVIDERS:
        raise AIError(f"Unknown AI provider {provider_id!r}.", "unknown_provider")
    return PROVIDERS[provider_id].info


def make_provider(
    provider_id: str, http: HttpClient, model: str, base_url: str = "", api_key: str = ""
) -> Provider:
    provider_info(provider_id)  # raises for unknown ids
    return PROVIDERS[provider_id](http, model=model, base_url=base_url, api_key=api_key)


# Words that usually mark a provider's cheaper, faster models.
_CHEAP_HINTS = ("haiku", "mini", "flash", "small", "lite")


def suggest_model(models: list[str]) -> str:
    """Pick a sensible default from a provider's model list."""
    for hint in _CHEAP_HINTS:
        for name in models:
            if hint in name.lower():
                return name
    return models[0] if models else ""
