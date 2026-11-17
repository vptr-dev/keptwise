"""Tests for each AI provider and the JSON helper, using a fake network."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.ai.base import AIError
from app.ai.http import HttpError
from app.ai.json_tools import chat_json, extract_json
from app.ai.providers.ollama import is_cloud_model
from app.ai.registry import make_provider, suggest_model
from tests.fakes import FakeNet

HELLO = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]


def test_ollama_chat_sends_schema_and_reads_reply() -> None:
    net = FakeNet().on("POST", "http://localhost:11434/api/chat", {"message": {"content": "hello"}})
    provider = make_provider("ollama", net.client(), model="gemma4:12b")
    assert provider.chat(HELLO, json_schema={"type": "object"}) == "hello"
    sent = net.requests[0]["json"]
    assert sent["model"] == "gemma4:12b" and sent["stream"] is False
    assert sent["format"] == {"type": "object"}


def test_ollama_turns_thinking_off_and_retries_if_refused() -> None:
    sent: list[dict] = []

    def reply(body: dict) -> dict:
        sent.append(body)
        if "think" in body:
            raise HttpError("HTTP 400", status=400, body='{"error":"model does not support think"}')
        return {"message": {"content": "hi"}}

    net = FakeNet().on("POST", "http://localhost:11434/api/chat", reply)
    provider = make_provider("ollama", net.client(), model="old-model:7b")
    assert provider.chat(HELLO) == "hi"
    assert sent[0]["think"] is False and "think" not in sent[1]


def test_ollama_missing_model_message() -> None:
    net = FakeNet().on("POST", "http://localhost:11434/api/chat", HttpError("HTTP 404", status=404))
    provider = make_provider("ollama", net.client(), model="gemma4:12b")
    with pytest.raises(AIError) as error:
        provider.chat(HELLO)
    assert error.value.code == "model_missing"


def test_ollama_not_running_message() -> None:
    provider = make_provider("ollama", FakeNet().client(), model="gemma4:12b")
    with pytest.raises(AIError) as error:
        provider.list_models()
    assert "Is it installed and running?" in str(error.value)
    assert error.value.code == "unreachable"


def test_openai_chat_uses_bearer_key_and_json_mode() -> None:
    net = FakeNet().on(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        {"choices": [{"message": {"content": "{}"}}]},
    )
    provider = make_provider("openai", net.client(), model="gpt-x", api_key="sk-123")
    provider.chat(HELLO, json_schema={})
    request = net.requests[0]
    assert request["headers"]["Authorization"] == "Bearer sk-123"
    assert request["json"]["response_format"] == {"type": "json_object"}


def test_cloud_provider_without_key_explains() -> None:
    provider = make_provider("openai", FakeNet().client(), model="gpt-x")
    with pytest.raises(AIError) as error:
        provider.chat(HELLO)
    assert error.value.code == "missing_key"


def test_bad_key_message() -> None:
    net = FakeNet().on("GET", "https://openrouter.ai/api/v1/models", HttpError("HTTP 401", status=401))
    provider = make_provider("openrouter", net.client(), model="m", api_key="bad")
    with pytest.raises(AIError) as error:
        provider.list_models()
    assert error.value.code == "bad_key"


def test_anthropic_puts_system_prompt_separately() -> None:
    net = FakeNet().on(
        "POST",
        "https://api.anthropic.com/v1/messages",
        {"content": [{"type": "text", "text": "hi there"}]},
    )
    provider = make_provider("anthropic", net.client(), model="claude-haiku-5-5", api_key="k")
    assert provider.chat(HELLO) == "hi there"
    request = net.requests[0]
    assert request["headers"]["x-api-key"] == "k"
    assert request["json"]["system"] == "Be brief."
    assert request["json"]["messages"] == [{"role": "user", "content": "Hi"}]


def test_anthropic_sends_no_temperature_and_skips_thinking_blocks() -> None:
    net = FakeNet().on(
        "POST",
        "https://api.anthropic.com/v1/messages",
        {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "answer"}]},
    )
    provider = make_provider("anthropic", net.client(), model="claude-haiku-5-5", api_key="k")
    assert provider.chat(HELLO, temperature=0.1) == "answer"
    body = net.requests[0]["json"]
    assert "temperature" not in body  # current Claude models reject it
    assert body["max_tokens"] == 16000


def test_anthropic_refusal_is_explained() -> None:
    net = FakeNet().on(
        "POST", "https://api.anthropic.com/v1/messages", {"stop_reason": "refusal", "content": []}
    )
    provider = make_provider("anthropic", net.client(), model="claude-haiku-5-5", api_key="k")
    with pytest.raises(AIError) as error:
        provider.chat(HELLO)
    assert error.value.code == "refused"


def test_openai_retries_without_temperature_when_model_rejects_it() -> None:
    sent: list[dict] = []

    def reply(body: dict) -> dict:
        sent.append(body)
        if "temperature" in body:
            raise HttpError("HTTP 400", status=400, body="Unsupported value: 'temperature'")
        return {"choices": [{"message": {"content": "ok"}}]}

    net = FakeNet().on("POST", "https://api.openai.com/v1/chat/completions", reply)
    provider = make_provider("openai", net.client(), model="gpt-x-mini", api_key="sk")
    assert provider.chat(HELLO) == "ok"
    assert len(sent) == 2 and "temperature" not in sent[1]


def test_ollama_cloud_models_get_no_schema_format() -> None:
    net = FakeNet().on("POST", "http://localhost:11434/api/chat", {"message": {"content": "{}"}})
    provider = make_provider("ollama", net.client(), model="gpt-oss:120b-cloud")
    provider.chat(HELLO, json_schema={"type": "object"})
    assert "format" not in net.requests[0]["json"]
    assert is_cloud_model("gpt-oss:120b-cloud") and is_cloud_model("kimi:cloud")
    assert not is_cloud_model("gemma4:12b") and not is_cloud_model("cloudy")


def test_gemini_maps_roles_and_lists_models() -> None:
    net = (
        FakeNet()
        .on(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent",
            {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )
        .on(
            "GET",
            "https://generativelanguage.googleapis.com/v1beta/models",
            {
                "models": [
                    {"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embed-only", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        )
    )
    provider = make_provider("gemini", net.client(), model="gemini-x", api_key="g")
    assert provider.chat(HELLO + [{"role": "assistant", "content": "Yo"}]) == "ok"
    body = net.requests[0]["json"]
    assert body["systemInstruction"]["parts"][0]["text"] == "Be brief."
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert provider.list_models() == ["gemini-x"]


def test_lmstudio_is_local_without_key() -> None:
    net = FakeNet().on("GET", "http://localhost:1234/v1/models", {"data": [{"id": "qwen"}]})
    provider = make_provider("lmstudio", net.client(), model="")
    assert provider.list_models() == ["qwen"]
    assert "Authorization" not in net.requests[0]["headers"]


def test_extract_json_handles_fences_and_chatter() -> None:
    assert extract_json('Sure! ```json\n{"a": 1}\n``` done') == '{"a": 1}'
    assert extract_json('Here: {"a": {"b": 2}} thanks') == '{"a": {"b": 2}}'
    with pytest.raises(ValueError):
        extract_json("no json here")


class Note(BaseModel):
    title: str
    steps: list[str]


def test_chat_json_repairs_a_bad_answer() -> None:
    replies = iter(['{"title": "Pasta"}', '{"title": "Pasta", "steps": ["Boil water"]}'])
    net = FakeNet().on("POST", "http://localhost:11434/api/chat", lambda _req: {"message": {"content": next(replies)}})
    provider = make_provider("ollama", net.client(), model="gemma4:12b")
    note = chat_json(provider, HELLO, Note)
    assert note == Note(title="Pasta", steps=["Boil water"])
    # The second request showed the model its mistake.
    assert "not valid" in net.requests[1]["json"]["messages"][-1]["content"]


def test_chat_json_gives_up_after_retries() -> None:
    net = FakeNet().on("POST", "http://localhost:11434/api/chat", {"message": {"content": "nope"}})
    provider = make_provider("ollama", net.client(), model="gemma4:12b")
    with pytest.raises(AIError) as error:
        chat_json(provider, HELLO, Note)
    assert error.value.code == "bad_json"
    assert len(net.requests) == 3


def test_suggest_model_prefers_cheap_models() -> None:
    assert suggest_model(["gpt-big", "gpt-mini"]) == "gpt-mini"
    assert suggest_model(["a", "b"]) == "a"
    assert suggest_model([]) == ""
