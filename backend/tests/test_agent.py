"""The AI Assistant doing things in the app: acting, asking first, undoing."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.items_repo import NewItem, upsert_item
from app.search.agent import Action, allowed, catalog, is_big, run_approved
from app.services import AppServices
from tests.fakes import FakeNet

OLLAMA = "http://localhost:11434"


class Script:
    """The AI's replies, one per call, and what it was shown."""

    def __init__(self, net: FakeNet, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": "gemma4:12b"}]})
        net.on("POST", f"{OLLAMA}/api/chat", self)

    def __call__(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        self.prompts.append(" ".join(m["content"] for m in payload["messages"]))
        return {"message": {"content": json.dumps(self.replies.pop(0))}}


def saves(svc: AppServices, *captions: str) -> list[int]:
    with svc.db.connect() as conn:
        return [upsert_item(conn, NewItem("tiktok", f"https://t/{n}", caption=c))[0] for n, c in enumerate(captions)]


def ask(api: TestClient, text: str) -> dict[str, Any]:
    chat = api.post("/api/assistant/chats", json={}).json()
    response = api.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def collection_saves(api: TestClient, name: str) -> list[int]:
    found = [c for c in api.get("/api/collections").json()["collections"] if c["name"] == name]
    if not found:
        return []
    items = api.get(f"/api/library/items?collection_id={found[0]['id']}").json()["items"]
    return sorted(i["id"] for i in items)


def test_the_ai_looks_things_up_makes_a_collection_and_files_saves(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    pasta, soup, gym = saves(svc, "Pasta night", "Pasta soup", "Leg day")
    script = Script(net, [
        {"mode": "act", "actions": [{"method": "GET", "path": "/api/library/items?q=pasta"}]},
        {"mode": "act", "actions": [{"method": "POST", "path": "/api/collections", "body": {"name": "Pasta"}, "why": "made Pasta"}]},
        {"mode": "act", "actions": [{"method": "POST", "path": "/api/items/bulk",
                                     "body": {"item_ids": [pasta, soup], "action": "add_to", "collection_id": 1},
                                     "why": "filed 2 saves"}]},
        {"mode": "done", "say": "Made Pasta and put 2 saves in it."},
    ])
    chat = ask(api, "put my pasta saves in a new collection called Pasta")
    last = chat["messages"][-1]
    assert last["content"] == "Made Pasta and put 2 saves in it."
    assert last["actions"]["state"] == "done" and last["actions"]["changed"] == ["made Pasta", "filed 2 saves"]
    assert collection_saves(api, "Pasta") == sorted([pasta, soup])
    # It saw the app's actions, the library and the lookup's results.
    assert "POST /api/items/bulk" in script.prompts[0] and "Pasta night" in script.prompts[1]

    # Everything it did is one Undo step.
    assert api.get("/api/undo").json()["undo"]["label"].startswith("AI: put my pasta saves")
    api.post("/api/undo")
    assert collection_saves(api, "Pasta") == [] and gym


def test_big_steps_wait_for_the_user(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    made = api.post("/api/collections", json={"name": "Gym"}).json()["created_id"]
    Script(net, [
        {"mode": "act", "say": "I'll delete the Gym collection.",
         "actions": [{"method": "DELETE", "path": f"/api/collections/{made}", "why": "deleted Gym"}]},
        {"mode": "done", "say": "Deleted Gym."},
    ])
    chat = ask(api, "delete gym")
    waiting = chat["messages"][-1]
    assert waiting["actions"]["state"] == "waiting" and waiting["actions"]["pending"][0]["method"] == "DELETE"
    assert any(c["name"] == "Gym" for c in api.get("/api/collections").json()["collections"])  # not yet

    done = api.post(f"/api/assistant/chats/{chat['id']}/messages/{waiting['id']}/confirm", json={"go": True}).json()
    assert done["messages"][-1]["content"] == "Deleted Gym."
    assert not any(c["name"] == "Gym" for c in api.get("/api/collections").json()["collections"])
    assert done["messages"][-2]["actions"]["state"] == "done"
    again = api.post(f"/api/assistant/chats/{chat['id']}/messages/{waiting['id']}/confirm", json={"go": True})
    assert again.status_code == 409


def test_cancel_leaves_everything(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    made = api.post("/api/collections", json={"name": "Gym"}).json()["created_id"]
    Script(net, [{"mode": "act", "actions": [{"method": "DELETE", "path": f"/api/collections/{made}"}]}])
    chat = ask(api, "delete gym")
    waiting = chat["messages"][-1]
    done = api.post(f"/api/assistant/chats/{chat['id']}/messages/{waiting['id']}/confirm", json={"go": False}).json()
    assert done["messages"][-2]["actions"]["state"] == "cancelled"
    assert any(c["name"] == "Gym" for c in api.get("/api/collections").json()["collections"])


def test_the_ai_can_undo_when_asked(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    api.post("/api/collections", json={"name": "Oops"})
    Script(net, [
        {"mode": "act", "actions": [{"method": "POST", "path": "/api/undo", "why": "undid New collection"}]},
        {"mode": "done", "say": "Undone."},
    ])
    ask(api, "undo that")
    assert not any(c["name"] == "Oops" for c in api.get("/api/collections").json()["collections"])


def test_it_cant_use_what_isnt_its_to_use(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    script = Script(net, [
        {"mode": "act", "actions": [{"method": "POST", "path": "/api/updates/install"},
                                    {"method": "PUT", "path": "/api/ai/providers/openai/key", "body": {"key": "x"}}]},
        {"mode": "done", "say": "I can't do that."},
    ])
    chat = ask(api, "update the app")
    assert chat["messages"][-1]["content"] == "I can't do that."
    assert "not allowed" in script.prompts[1]


def test_questions_about_the_saves_are_answered_as_before(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    saves(svc, "Pasta night")
    Script(net, [{"mode": "answer"}])
    with pytest.raises(IndexError):  # the usual answer step asks the AI next (this script has no reply for it)
        api.post(f"/api/assistant/chats/{api.post('/api/assistant/chats', json={}).json()['id']}/messages",
                 json={"content": "what pasta did I save?"})


def test_assistant_cannot_confirm_a_paid_batch_for_the_user(api: TestClient) -> None:
    seen = []

    def call(method: str, path: str, body: dict[str, Any] | None, step: int) -> tuple[int, Any]:
        seen.append(body)
        return 409, {"code": "confirm_cost"}

    run_approved(
        call, catalog(api.app),
        [{"method": "POST", "path": "/api/notes/start", "body": {"count": 10, "confirm_cost": True}}],
        {}, 1,
    )
    assert seen == [{"count": 10, "confirm_cost": False}]


def test_what_counts_as_big(api: TestClient) -> None:
    assert is_big([Action(method="DELETE", path="/api/collections/3")])
    assert is_big([Action(method="POST", path="/api/items/bulk", body={"action": "delete", "item_ids": [1]})])
    assert is_big([Action(method="POST", path="/api/items/bulk", body={"action": "add_tag", "item_ids": list(range(20))})])
    assert not is_big([Action(method="POST", path="/api/items/bulk", body={"action": "add_tag", "item_ids": [1, 2]})])
    assert not is_big([Action(method="PATCH", path="/api/collections/3", body={"name": "x"})])
    assert not is_big([Action(method="DELETE", path="/api/items/4/tags/2")])
    actions = catalog(api.app)
    assert allowed(Action(method="PATCH", path="/api/collections/12"), actions)
    assert not allowed(Action(method="POST", path="/api/updates/install"), actions)
    assert not allowed(Action(method="POST", path="/api/storage/clear"), actions)


def test_changing_the_look_keeps_the_other_settings(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    current = api.get("/api/ui").json()
    api.put("/api/ui", json={**current, "welcomed": True, "name": "Sam"})
    Script(net, [
        {"mode": "act", "actions": [{"method": "PUT", "path": "/api/ui", "body": {"accent": "rose"}}]},
        {"mode": "done", "say": "Rose it is."},
    ])
    ask(api, "make the app pink")
    after = api.get("/api/ui").json()
    assert after["accent"] == "rose" and after["welcomed"] is True and after["name"] == "Sam"


def test_changes_sent_with_a_lookup_wait_for_its_results(api: TestClient, svc: AppServices, net: FakeNet) -> None:
    (pasta,) = saves(svc, "Pasta night")
    script = Script(net, [
        {"mode": "act", "actions": [{"method": "GET", "path": "/api/library/items?q=pasta"},
                                    {"method": "POST", "path": "/api/items/bulk",
                                     "body": {"item_ids": [0], "action": "add_tag", "tag": "dinner"}}]},
        {"mode": "act", "actions": [{"method": "POST", "path": "/api/items/bulk",
                                     "body": {"item_ids": [pasta], "action": "add_tag", "tag": "dinner"}}]},
        {"mode": "done", "say": "Tagged 1 save dinner."},
    ])
    ask(api, "tag my pasta saves dinner")
    assert "were not run" in script.prompts[1]
    assert api.get("/api/library/items?tag=dinner").json()["total"] == 1
