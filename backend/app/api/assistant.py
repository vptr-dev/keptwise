"""Routes for the AI Assistant: saved chats and the AI tools."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.sorting import cards_by_id
from app.library import scope
from app.search import assistant
from app.services import AppServices, services

router = APIRouter(prefix="/api/assistant")


class Target(BaseModel):
    type: Literal["all", "collection", "tag", "plan", "items"] = "all"
    id: int | None = None
    name: str | None = Field(default=None, max_length=80)
    ids: list[int] | None = Field(default=None, max_length=assistant.MAX_PICKED)  # for "items": the saves picked


class NewChat(BaseModel):
    tool: Literal["ask", "summary", "plan", "shopping", "compare", "takeaways"] = "ask"
    target: Target | None = None
    title: str | None = Field(default=None, max_length=80)


class ChatPatch(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


def _with_cards(svc: AppServices, chat: dict[str, Any]) -> dict[str, Any]:
    """Put the save cards next to each answer's sources."""
    ids = [s["item_id"] for m in chat.get("messages", []) for s in m["sources"]]
    with svc.db.connect() as conn:
        cards = cards_by_id(conn, list(dict.fromkeys(ids)))
    for message in chat.get("messages", []):
        message["sources"] = [s | {"item": cards[s["item_id"]]} for s in message["sources"] if s["item_id"] in cards]
    return chat


@router.get("/tools")
def tools() -> dict[str, Any]:
    return {
        "tools": [
            {"id": tool, "label": assistant.TOOL_LABELS[tool], "prompt": assistant.DEFAULT_PROMPTS.get(tool)}
            for tool in assistant.TOOLS
        ]
    }


@router.get("/chats")
def list_chats(svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        return {"chats": assistant.list_chats(conn)}


@router.post("/chats")
def create_chat(body: NewChat, svc: AppServices = Depends(services)) -> dict[str, Any]:
    target = body.target.model_dump(exclude_none=True) if body.target and body.target.type != "all" else None
    if target and target["type"] == "items" and not target.get("ids"):
        raise HTTPException(status_code=400, detail="Pick the saves to ask about first.")
    with svc.db.connect() as conn:
        try:
            chat_id = assistant.create_chat(conn, body.tool, target, body.title)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return assistant.get_chat(conn, chat_id) or {}


@router.get("/chats/{chat_id}")
def get_chat(chat_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        chat = assistant.get_chat(conn, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="That chat doesn't exist any more.")
    return _with_cards(svc, chat)


@router.patch("/chats/{chat_id}")
def rename_chat(chat_id: int, body: ChatPatch, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        try:
            assistant.rename_chat(conn, chat_id, body.title)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return get_chat(chat_id, svc)


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: int, svc: AppServices = Depends(services)) -> dict[str, Any]:
    with svc.db.connect() as conn:
        assistant.delete_chat(conn, chat_id)
    return list_chats(svc)


@router.post("/chats/{chat_id}/messages")
def send_message(chat_id: int, body: MessageBody, svc: AppServices = Depends(services)) -> dict[str, Any]:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Type a message first.")
    try:
        chat = assistant.send(svc.db, svc.search, svc.ai, chat_id, content, scope.current(svc.settings))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    return _with_cards(svc, chat)
