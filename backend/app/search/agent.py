"""The AI Assistant doing things in the app for the user.

The AI is shown the app's own actions (the same API the screens use, listed
from the routes themselves, so anything the app can do, the AI can do) and
the user's collections, spaces, tags and plans. It answers with actions; the
app runs them through its normal API, so every check the screens get, the
AI gets too, and it reads the results before its next move.

Safety:
- Big steps (deleting, merging, moving many saves, anything touching more
  than a handful of things) wait for the user to press "Do it".
- Everything the AI changes in one go is one Undo step ("AI: ..."), and the
  AI can undo or redo itself when asked.
- It can't touch settings outside the library, API keys, updates, imports
  or the user's files.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.base import AIError, Message

MAX_ROUNDS = 8
RESULT_CHARS = 1500
# The AI's notes so far: the newest are kept, so the whole prompt stays inside
# Ollama's 8192-token window (switching sizes makes Ollama reload the model).
ROUNDS_CHARS = 6000
SMALL_BATCH = 10  # more changes, or more saves, than this at once: ask first

# What the AI may use. Everything about the user's library; nothing about
# keys, updates, imports, storage or the app's own machinery.
ALLOWED = re.compile(
    r"^/api/(library(/items|/filters)?|overview|archive|unsave|scope|ui|collections(?!/\{collection_id\}/icon)"
    r"|spaces|tags|items|plans|review|platform-collections|search|sorting/(resort|clear)|tags/ai|notes/start"
    r"|enrich/start|jobs|undo|redo)"
)
NOT_FOR_AI = re.compile(r"/archive/batch/|/thumbnail$|/search/(status|index)$|\.csv$|/export$|/open-folder$|/open$|/dismiss-notice$")
BIG_PATHS = re.compile(r"/merge$|/tags/delete$|/collections/bulk$|/platform-collections(?:/(apply|transfer|default))?$|/sorting/(resort|clear)$"
                       r"|/review/accept-all$|/unsave/clear$")
BIG_BULK = {"delete", "purge", "move_to", "remove_from", "unsaved"}

Caller = Callable[[str, str, dict[str, Any] | None, int], tuple[int, Any]]


class Action(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(max_length=300)
    body: dict[str, Any] | None = None
    why: str = Field(default="", max_length=200)


class AgentReply(BaseModel):
    mode: Literal["chat", "clarify", "answer", "act", "done"]
    actions: list[Action] = Field(default_factory=list, max_length=30)
    say: str = ""
    title: str = Field(default="", max_length=80)


RULES = (
    "You are the AI Assistant inside Keptwise, a desktop app where the user keeps the videos and posts they "
    "saved on TikTok, YouTube, Instagram and Facebook, organised into collections (inside spaces), tags and plans.\n"
    "Talk like a helpful person. Choose a mode based on what the user wants.\n"
    "- chat: talk, explain how Keptwise works, brainstorm, or respond to greetings. Put the reply in say. "
    "Never make changes for conversation, advice or suggestions.\n"
    "- clarify: ask one specific question if an edit's target or outcome is ambiguous. Use the user's next reply.\n"
    "- answer: retrieve and cite saves for questions about their contents.\n"
    "- act: look up saves or execute explicit edit requests only. Never claim a change unless it succeeded.\n"
    "Fill title with a short topic of six words or fewer for the first substantive request.\n"
    "How to act:\n"
    "- For requests to find or show saves, use answer mode or GET /api/search. Never edit saves in a lookup.\n"
    "- Use only the actions listed, with real ids from the data below or from earlier results. Never invent ids.\n"
    "- When you need ids you don't have (which saves match something, a collection's contents), use GET actions "
    "first; their results come back to you and you can act after.\n"
    "- Do exactly what the user asked, as specifically as they asked, no more.\n"
    "- If a paid batch needs confirmation, tell the user to start it from Sort, where they can see the cost prompt.\n"
    "- A reply with GET actions should have only GET actions: changes come in a later reply, once you've seen "
    "the results (real ids, never 0 or made-up ones).\n"
    "- If an action fails because of a limit or a rule (for example the most tags allowed), stop and explain it "
    'in "say" with what the user could do. Never work around it by deleting, merging or changing other things.\n'
    "- Prefer one bulk action (POST /api/items/bulk) over many single ones for several saves.\n"
    '- "Undo that" / "take that back" means POST /api/undo (one call takes back one step, yours included). '
    '"Redo" / "put it back" means POST /api/redo. Never rebuild things by hand instead.\n'
    '- When everything is done, or it can\'t be done, reply {"mode": "done", "say": "..."}: one or two plain '
    "sentences saying what you did (with names and numbers) or why not.\n"
    "- Write \"say\" in the user's language. Reply with JSON only.\n"
    "Examples:\n"
    'User: make a collection called Gym -> {"mode": "act", "actions": [{"method": "POST", "path": "/api/collections", '
    '"body": {"name": "Gym"}, "why": "made the Gym collection"}], "say": ""}\n'
    'User: tag my pasta videos dinner -> {"mode": "act", "actions": [{"method": "GET", "path": '
    '"/api/library/items?q=pasta"}], "say": ""} then, with the ids from the result, {"mode": "act", "actions": '
    '[{"method": "POST", "path": "/api/items/bulk", "body": {"item_ids": [12, 40], "action": "add_tag", "tag": '
    '"dinner"}, "why": "tagged 2 pasta saves dinner"}], "say": ""}\n'
    'User: what pasta recipes did I save? -> {"mode": "answer"}\n'
    'After the results show it worked -> {"mode": "done", "say": "Made the Gym collection."}'
)


# ---------- the actions the app has ----------


def _fields(model: Any) -> str:
    try:
        schema = model.model_json_schema()
    except Exception:  # noqa: BLE001 - not a pydantic model
        return ""
    props = schema.get("properties", {})
    parts = []
    for name, info in props.items():
        kind = info.get("type") or "/".join(
            str(o.get("type") or o.get("$ref", "").rsplit("/", 1)[-1]) for o in info.get("anyOf", [])
        )
        if "enum" in info:
            kind = "|".join(map(str, info["enum"]))
        elif info.get("items", {}).get("enum"):
            kind = "list of " + "|".join(map(str, info["items"]["enum"]))
        for option in info.get("anyOf", []):
            if "enum" in option:
                kind = "|".join(map(str, option["enum"]))
        parts.append(f"{name}: {kind}")
    return ", ".join(parts)


def catalog(app: Any) -> list[dict[str, str]]:
    """Every API action the AI may use, read from the app's routes."""
    from fastapi.routing import APIRoute

    def walk(routes: list[Any]) -> list[Any]:
        flat = []
        for route in routes:
            inner = getattr(route, "original_router", None)  # newer FastAPI wraps included routers
            flat += walk(inner.routes) if inner is not None else [route]
        return flat

    found = []
    for route in walk(list(app.routes)):
        if not isinstance(route, APIRoute) or not ALLOWED.match(route.path):
            continue
        for method in sorted(route.methods or []):
            if method == "HEAD" or NOT_FOR_AI.search(route.path) or (route.path.startswith("/api/jobs") and method != "GET"):
                continue
            body = getattr(route.body_field, "field_info", None) and route.body_field.field_info.annotation  # type: ignore[union-attr]
            query = [p.name for p in route.dependant.query_params if p.name != "svc"]
            doc = (route.endpoint.__doc__ or "").strip().splitlines()
            found.append({
                "method": method,
                "path": route.path,
                "query": ", ".join(query),
                "body": _fields(body) if body is not None else "",
                "about": doc[0] if doc else route.endpoint.__name__.replace("_", " "),
            })
    return found


def catalog_text(actions: list[dict[str, str]]) -> str:
    lines = []
    for a in actions:
        line = f"{a['method']} {a['path']}"
        if a["query"]:
            line += f"?{a['query']}"
        if a["body"]:
            line += f"  body {{{a['body']}}}"
        line += f"  - {a['about']}"
        lines.append(line)
    return "\n".join(lines)


def _route_pattern(path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(path)) + "$")


def allowed(action: Action, actions: list[dict[str, str]]) -> bool:
    path = action.path.split("?", 1)[0]
    return any(a["method"] == action.method and _route_pattern(a["path"]).match(path) for a in actions)


def is_big(changes: list[Action]) -> bool:
    """Steps the user should see before they happen."""
    affected = sum(
        max(1, len(action.body["item_ids"])) if isinstance((action.body or {}).get("item_ids"), list) else 1
        for action in changes
    )
    if affected > SMALL_BATCH:
        return True
    for change in changes:
        path = change.path.split("?", 1)[0]
        body = change.body or {}
        if change.method == "DELETE" and not re.search(r"/(tags|items)/\d+/(tags|collections)/\d+$", path):
            return True
        if BIG_PATHS.search(path):
            return True
        if path.endswith("/items/bulk") and (body.get("action") in BIG_BULK or len(body.get("item_ids") or []) > SMALL_BATCH):
            return True
        if path.endswith("/undo") or path.endswith("/redo"):
            continue
        if change.method == "PATCH" and re.search(r"/items/\d+$", path) and body.get("deleted"):
            return True
    return False


# ---------- what the AI sees ----------


def library_data(conn: sqlite3.Connection) -> str:
    """Ids and names the AI can act on without looking them up."""
    lines = []
    spaces = conn.execute("SELECT id, name FROM spaces ORDER BY position, id").fetchall()
    if spaces:
        lines.append("Spaces: " + "; ".join(f"{r['id']}={r['name']}" for r in spaces))
    rows = conn.execute(
        """SELECT c.id, c.name, c.parent_id, c.space_id,
                  (SELECT COUNT(*) FROM item_collections ic JOIN items i ON i.id = ic.item_id
                   WHERE ic.collection_id = c.id AND i.deleted_at IS NULL) AS n
           FROM collections c ORDER BY c.space_id, c.parent_id, c.position, c.id LIMIT 300"""
    ).fetchall()
    if rows:
        lines.append("Collections (id=name [space, inside, saves]): " + "; ".join(
            f"{r['id']}={r['name']} [s{r['space_id']}{', in ' + str(r['parent_id']) if r['parent_id'] else ''}, {r['n']}]"
            for r in rows
        ))
    tags = conn.execute(
        "SELECT t.id, t.name, COUNT(it.item_id) AS n FROM tags t LEFT JOIN item_tags it ON it.tag_id = t.id "
        "GROUP BY t.id ORDER BY n DESC LIMIT 200"
    ).fetchall()
    if tags:
        lines.append("Tags (id=name saves): " + "; ".join(f"{r['id']}={r['name']} {r['n']}" for r in tags))
    plans = conn.execute("SELECT id, name FROM plans ORDER BY id DESC LIMIT 60").fetchall()
    if plans:
        lines.append("Plans: " + "; ".join(f"{r['id']}={r['name']}" for r in plans))
    try:
        done = conn.execute("SELECT label FROM undo_steps WHERE state = 'done' ORDER BY id DESC LIMIT 1").fetchone()
        undone = conn.execute("SELECT label FROM undo_steps WHERE state = 'undone' ORDER BY id LIMIT 1").fetchone()
    except sqlite3.Error:
        done = undone = None
    lines.append(
        f"Undo (POST /api/undo) would take back: {done[0] if done else 'nothing'}. "
        f"Redo (POST /api/redo) would put back: {undone[0] if undone else 'nothing'}."
    )
    total = conn.execute("SELECT COUNT(*) FROM items WHERE deleted_at IS NULL").fetchone()[0]
    lines.append(f"{total} saves in all. Find saves with GET /api/library/items?q=words (or collection_id, tag, ...).")
    return "\n".join(lines)


def compact(value: Any, depth: int = 0) -> Any:
    """Results trimmed to what helps the AI decide (ids, names, counts)."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(word in key for word in ("thumb", "icon_url", "transcript", "embedding", "steps", "facts")):
                continue
            out[key] = compact(item, depth + 1)
        return out
    if isinstance(value, list):
        trimmed = [compact(v, depth + 1) for v in value[:40]]
        return trimmed + ([f"...and {len(value) - 40} more"] if len(value) > 40 else [])
    if isinstance(value, str) and len(value) > 160:
        return value[:160] + "…"
    return value


def result_text(action: Action, status: int, body: Any) -> str:
    text = json.dumps(compact(body), ensure_ascii=False, separators=(",", ":"))
    if len(text) > RESULT_CHARS:
        text = text[:RESULT_CHARS] + "…(cut)"
    return f"{action.method} {action.path} -> {status} {text}"


def messages(question_history: list[Message], data: str, actions: str, rounds: list[str]) -> list[Message]:
    turns = [m for m in question_history if m.get("role") in ("user", "assistant")][-8:]
    earlier, question = turns[:-1], (turns[-1]["content"] if turns else "")
    parts = [f"The user's library:\n{data}", f"Actions you can use:\n{actions}"]
    if earlier:
        parts.append("Conversation so far:\n" + "\n".join(f"{m['role']}: {m['content'][:600]}" for m in earlier))
    parts.append(f"The user says: {question}")
    if rounds:
        kept: list[str] = []
        for line in reversed(rounds):
            if sum(len(k) for k in kept) + len(line) > ROUNDS_CHARS:
                break
            kept.insert(0, line)
        parts.append("What you've done so far in this request, and the results:\n" + "\n".join(kept))
    parts.append(
        'Reply as JSON: {"mode": "chat" | "clarify" | "answer" | "act" | "done", "actions": [{"method": "...", "path": "/api/...", '
        '"body": {...}, "why": "short"}], "say": "..."}'
    )
    return [{"role": "system", "content": RULES}, {"role": "user", "content": "\n\n".join(parts)}]


# ---------- running it ----------


def run(
    chat_json: Callable[[list[Message], type[AgentReply]], AgentReply],
    call: Caller,
    actions: list[dict[str, str]],
    data: str,
    history: list[Message],
    state: dict[str, Any],
    step: int,
    *,
    allow_changes: bool = True,
) -> dict[str, Any]:
    """Go round: ask the AI, run what it asks for, show it the results.

    Returns {"mode": "answer"} (a question about the saves: answer it the
    usual way), {"mode": "done", "say", "changed"} or {"mode": "waiting",
    "say", "pending", "state"} (big steps waiting for "Do it")."""
    rounds: list[str] = state.setdefault("rounds", [])
    changed: list[str] = state.setdefault("changed", [])
    title = ""
    edits: list[Action] = []
    text = catalog_text(actions)
    for _ in range(MAX_ROUNDS):
        try:
            reply = chat_json(messages(history, data, text, rounds), AgentReply)
        except AIError as error:
            if changed:
                return {"mode": "done", "say": _summary(changed), "changed": changed, "title": title}
            if rounds or getattr(error, "code", "") != "bad_json":
                raise
            return {"mode": "answer"}  # the model can't do actions: answer from the saves as before
        title = title or reply.title
        if reply.mode == "answer" and not changed:
            return {"mode": "answer", "title": title}
        if reply.mode in ("chat", "clarify") and reply.say.strip():
            return {"mode": reply.mode, "say": reply.say.strip(), "changed": changed, "title": title}
        if reply.mode != "act" or not reply.actions:
            return {"mode": "done", "say": reply.say.strip() or _summary(changed), "changed": changed, "rounds": rounds, "title": title}
        rounds.append("You asked for: " + json.dumps([a.model_dump(exclude_none=True) for a in reply.actions], ensure_ascii=False))
        looks = [a for a in reply.actions if a.method == "GET"]
        if looks and len(looks) < len(reply.actions):
            # Changes sent with a lookup can't use its results yet: look first.
            _run_all(call, looks, actions, rounds, changed, step)
            rounds.append("Your changes in that reply were not run: send them again now that you have the results.")
            continue
        changes = [a for a in reply.actions if a.method != "GET"]
        if changes and not allow_changes:
            return {"mode": "clarify", "say": "What would you like me to change?", "changed": changed, "title": title}
        if changes and is_big(edits + changes):
            _run_all(call, [a for a in reply.actions if a.method == "GET"], actions, rounds, changed, step)
            return {
                "mode": "waiting",
                "say": "Here’s what I’m proposing.",
                "title": title,
                "pending": [a.model_dump(exclude_none=True) for a in changes],
                "state": state,
            }
        _run_all(call, reply.actions, actions, rounds, changed, step)
        edits.extend(changes)
    return {"mode": "done", "say": _summary(changed) + " I stopped there: it was taking too many steps.", "changed": changed}


def run_approved(call: Caller, actions: list[dict[str, str]], pending: list[dict[str, Any]],
                 state: dict[str, Any], step: int) -> None:
    """The user pressed "Do it": run the waiting changes."""
    rounds: list[str] = state.setdefault("rounds", [])
    changed: list[str] = state.setdefault("changed", [])
    _run_all(call, [Action(**a) for a in pending], actions, rounds, changed, step)


def _run_all(call: Caller, todo: list[Action], actions: list[dict[str, str]], rounds: list[str],
             changed: list[str], step: int) -> None:
    for action in todo:
        if not allowed(action, actions):
            rounds.append(f"{action.method} {action.path} -> not allowed: that action doesn't exist or isn't yours to use")
            continue
        try:
            payload = action.body
            if payload and "confirm_cost" in payload:
                payload = {**payload, "confirm_cost": False}
            status, body = call(action.method, action.path, payload, step)
        except Exception as error:  # noqa: BLE001 - one failed action is reported, not fatal
            status, body = 500, {"detail": str(error)}
        rounds.append(result_text(action, status, body))
        if action.method != "GET" and status < 400:
            changed.append(action.why or f"{action.method} {action.path}")


def _summary(changed: list[str]) -> str:
    if not changed:
        return "I didn't change anything."
    return "Done: " + "; ".join(changed[:8]) + ("…" if len(changed) > 8 else "") + "."
