"""Getting reliable JSON answers out of an AI model.

chat_json() asks for JSON matching a pydantic model. If the answer isn't
valid, it shows the model its mistake and asks again (up to 2 repairs).
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.base import AIError, Message, Provider

T = TypeVar("T", bound=BaseModel)

REPAIR_RETRIES = 2

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may have extra words around it."""
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("The answer contained no JSON object.")
    return text[start : end + 1]


def _schema_instructions(schema: dict[str, object]) -> str:
    return (
        "Reply with ONLY a JSON object, no other text, that matches this JSON schema:\n"
        + json.dumps(schema)
    )


def chat_json(
    provider: Provider,
    messages: list[Message],
    model_cls: type[T],
    temperature: float = 0.1,
) -> T:
    schema = model_cls.model_json_schema()
    conversation = list(messages) + [{"role": "user", "content": _schema_instructions(schema)}]
    # Only ask for strict schema mode where the provider supports it.
    strict = schema if provider.info.supports_schema else {}
    last_problem = ""
    for _attempt in range(REPAIR_RETRIES + 1):
        reply = provider.chat(conversation, json_schema=strict, temperature=temperature)
        try:
            return model_cls.model_validate_json(extract_json(reply))
        except (ValueError, ValidationError) as error:
            last_problem = str(error)[:500]
            conversation += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": "That answer was not valid. Problem: "
                    + last_problem
                    + "\nReply again with ONLY the corrected JSON object.",
                },
            ]
    raise AIError(
        f"The AI didn't return usable results after {REPAIR_RETRIES + 1} tries. "
        f"Last problem: {last_problem}",
        "bad_json",
    )
