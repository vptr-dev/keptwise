"""Routes for the AI Assistant: saved chats and the AI tools."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.sorting import cards_by_id
from app.library import scope
from app.search import agent, assistant
from app.db.undo import UNDO_STEP_HEADER
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


class AgentTools:
    """How the AI's actions run: through this same app's API, as the user,
    each one recorded in the AI's Undo step."""

    def __init__(self, request: Request, svc: AppServices) -> None:
        from starlette.testclient import TestClient

        from app.api.session import TOKEN_HEADER

        self._client = TestClient(
            request.app, raise_server_exceptions=False, headers={TOKEN_HEADER: request.app.state.session_token}
        )
        self._undo = svc.db.undo
        self.actions = agent.catalog(request.app)

    def call(self, method: str, path: str, body: dict[str, Any] | None, step: int) -> tuple[int, Any]:
        if method == "PUT" and path.split("?")[0] == "/api/ui":
            # The look settings are saved whole: change only what the AI named.
            body = {**self._client.get("/api/ui").json(), **(body or {})}
        response = self._client.request(
            method, path, json=body if method != "GET" else None, headers={UNDO_STEP_HEADER: str(step)}
        )
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, response.text[:500]

    def new_step(self) -> int:
        return self._undo.new_step() if self._undo is not None else 0

    def finish(self, step: int, label: str) -> None:
        if self._undo is not None:
            self._undo.finish(step, label)


class ConfirmBody(BaseModel):
    go: bool


@router.post("/chats/{chat_id}/messages")
def send_message(chat_id: int, body: MessageBody, request: Request,
                 svc: AppServices = Depends(services)) -> dict[str, Any]:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Type a message first.")
    try:
        chat = assistant.send(svc.db, svc.search, svc.ai, chat_id, content, scope.current(svc.settings),
                              AgentTools(request, svc))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    return _with_cards(svc, chat)


@router.post("/chats/{chat_id}/messages/{message_id}/confirm")
def confirm_actions(chat_id: int, message_id: int, body: ConfirmBody, request: Request,
                    svc: AppServices = Depends(services)) -> dict[str, Any]:
    """The user's answer to big changes the AI is waiting to make."""
    try:
        chat = assistant.confirm(svc.db, svc.ai, chat_id, message_id, body.go, AgentTools(request, svc))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _with_cards(svc, chat)
