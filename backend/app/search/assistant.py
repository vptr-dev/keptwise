"""The AI Assistant: saved chats, and tools that work on a group of saves.

Every chat is kept (chats + chat_messages), so the user can come back to
it, rename it or delete it. A chat has a tool:

- ask:      questions answered only from the saves (found by search), like
            the old "Ask your saves". Can be limited to one collection, tag
            or plan.
- summary:  what's in a collection, tag or plan, grouped, with the best bits.
- plan:     turn a group of saves into an ordered plan of action; the
            window can then save the saves it used as a real Plan.
- shopping: one combined shopping or packing list from the saves' details.
- compare:  help choose between the saves (which recipe tonight, which
            place first), with reasons.
- takeaways: the most useful tips, facts and lessons across the saves.

A chat is about all saves, a collection, a tag, a plan, or saves the user
picked (target type "items": right-click picked saves -> Ask the AI).

All of them use only the saves given to the AI and cite them like [1], so
the window shows the saves an answer came from. Follow-up messages in a chat
keep the same tool and group.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from app.ai.base import Message
from app.ai.service import AIService
from app.db.connection import Database
from app.search import agent
from app.search.chat import NOTHING_FOUND, ChatAnswer, cited_numbers, describe_source, retrieval_query
from app.search.service import HybridHit, SearchService

Tool = Literal["ask", "summary", "plan", "shopping", "compare", "takeaways"]
TOOLS: tuple[str, ...] = ("ask", "summary", "plan", "shopping", "compare", "takeaways")
TargetType = Literal["all", "collection", "tag", "plan", "items"]

MAX_ASK_SOURCES = 8
MAX_GROUP_SOURCES = 15
MAX_PICKED = 30  # saves the user can bring into one chat
# How much of each transcript the AI reads: more when there are few saves.
TRANSCRIPT_BUDGET = 12000
HISTORY_TURNS = 8
SEARCH_POOL = 40

TOOL_LABELS = {
    "ask": "Ask anything",
    "summary": "Summarise",
    "plan": "Make a plan",
    "shopping": "Shopping or packing list",
    "compare": "Help me choose",
    "takeaways": "Key takeaways",
}

BASE_RULES = (
    "You are the AI Assistant inside Keptwise, an app where someone keeps the short videos and posts they saved "
    "on TikTok, YouTube, Instagram and Facebook, so the useful things in them don't get lost. For each save you "
    "are given: its title, who made it, the kind of video, where the user filed it (collections and tags), the "
    "caption, AI notes with key details and steps, and what was said in it (the transcript).\n"
    "How to answer:\n"
    "- Use ONLY the numbered saves (and the library overview, for questions about the library as a whole). "
    "Never add facts, amounts, prices, places or steps from your own knowledge. If the saves don't cover "
    "something, say so plainly instead of guessing.\n"
    "- Be specific: give the exact amounts, names, places, times and steps the saves give. The transcript "
    "usually has the detail the notes leave out, so read it.\n"
    "- Cite the saves you use like [1] or [2][3] right after the sentence they support.\n"
    "- Be practical and brief: lead with the answer, then the detail. Use '* ' bullet lines for lists, "
    "'1. ' lines for steps in order, and **bold** for short headings. No preamble, no closing summary.\n"
    "- When several saves say different things, say which says what. When one is clearly the best fit, say so.\n"
    "- Follow-up messages are about the same saves: use the conversation so far.\n"
    "- Write in the language the user writes in."
)

TOOL_INSTRUCTIONS = {
    "ask": "Answer the question from the saves. If they don't answer it, set found to false and say so briefly.",
    "summary": (
        "Summarise these saves: group them into a few themes with a short heading each, say in one line what "
        "each save is, and finish with the 2 or 3 that look most worth doing first and why."
    ),
    "plan": (
        "Turn these saves into a practical plan: an ordered list of steps (what to do first, what to buy or "
        "book, what to do on the day). Each step cites the save it comes from. Leave out saves that don't fit "
        "the plan, and put the numbers of the saves the plan uses in sources."
    ),
    "shopping": (
        "Make one combined shopping or packing list from the key details of these saves (ingredients, "
        "products, gear, things to bring). Merge duplicates and add up amounts when they're the same unit. "
        "Group it (for example by shop section), and cite which save each thing is for."
    ),
    "compare": (
        "Help the user choose between these saves: compare them on what matters (time, cost, effort, "
        "difficulty, what's needed), then recommend one or two with a clear reason. If the user says what "
        "they want, use that."
    ),
    "takeaways": (
        "Pull out the most useful things in these saves: the tips, facts, lessons and warnings worth "
        "remembering. Group them under a few short headings, one line each, most useful first, and cite the "
        "save each one comes from. Skip filler and anything the saves only hint at."
    ),
}

DEFAULT_PROMPTS = {
    "summary": "Summarise what's in {name}.",
    "plan": "Turn {name} into a plan I can follow.",
    "shopping": "Make a shopping list for {name}.",
    "compare": "Help me choose from {name}.",
    "takeaways": "What are the key takeaways from {name}?",
}


# ---------- the saves a chat works on ----------


def target_name(conn: sqlite3.Connection, target: dict[str, Any] | None) -> str:
    if not target or target.get("type") in (None, "all"):
        return "all my saves"
    kind, ref = target["type"], target.get("id")
    if kind == "collection":
        row = conn.execute("SELECT name FROM collections WHERE id = ?", (ref,)).fetchone()
        return f"my {row['name']} collection" if row else "a collection that's gone"
    if kind == "tag":
        return f"my saves tagged #{target.get('name')}"
    if kind == "plan":
        row = conn.execute("SELECT name FROM plans WHERE id = ?", (ref,)).fetchone()
        return f"my plan “{row['name']}”" if row else "a plan that's gone"
    if kind == "items":
        count = len(target.get("ids") or [])
        return "the save I picked" if count == 1 else f"the {count} saves I picked"
    return "my saves"


def library_overview(conn: sqlite3.Connection, platform: str | None) -> str:
    """A few lines about the whole library, so the AI can answer questions
    like "what do I save most?" and knows the user's own words for things."""
    scope_sql, params = ("deleted_at IS NULL AND platform = ?", [platform]) if platform else ("deleted_at IS NULL", [])
    row = conn.execute(
        f"SELECT COUNT(*) AS total, SUM(status = 'processed') AS noted FROM items WHERE {scope_sql}", params
    ).fetchone()
    lines = [f"{int(row['total'] or 0)} saves in all, {int(row['noted'] or 0)} with AI notes."]
    filed = conn.execute(
        """SELECT c.name, COUNT(i.id) AS n FROM collections c
           LEFT JOIN item_collections ic ON ic.collection_id = c.id
           LEFT JOIN items i ON i.id = ic.item_id AND i.deleted_at IS NULL
           GROUP BY c.id HAVING n > 0 ORDER BY n DESC LIMIT 25"""
    ).fetchall()
    if filed:
        lines.append("Collections (saves in each): " + ", ".join(f"{r['name']} ({r['n']})" for r in filed))
    used = conn.execute(
        """SELECT t.name, COUNT(*) AS n FROM tags t JOIN item_tags it ON it.tag_id = t.id
           JOIN items i ON i.id = it.item_id AND i.deleted_at IS NULL
           WHERE it.source <> 'auto' GROUP BY t.id ORDER BY n DESC LIMIT 30"""
    ).fetchall()
    if used:
        lines.append("Most used tags: " + ", ".join(f"{r['name']} ({r['n']})" for r in used))
    kinds = conn.execute(
        f"""SELECT a.kind, COUNT(*) AS n FROM ai_results a JOIN items i ON i.id = a.item_id
            WHERE a.kind IS NOT NULL AND {scope_sql.replace('deleted_at', 'i.deleted_at').replace('platform', 'i.platform')}
            GROUP BY a.kind ORDER BY n DESC""",
        params,
    ).fetchall()
    if kinds:
        lines.append("Kinds of video: " + ", ".join(f"{r['kind']} ({r['n']})" for r in kinds))
    return "\n".join(lines)


def target_items(conn: sqlite3.Connection, target: dict[str, Any] | None, platform: str | None,
                 limit: int | None = None) -> list[int]:
    """The saves in the chat's group (collection, tag or plan; every save for
    "all"), best first: ones with AI notes, then newest."""
    kind = (target or {}).get("type") or "all"
    scope_sql, params = ("i.deleted_at IS NULL AND i.platform = ?", [platform]) if platform else ("i.deleted_at IS NULL", [])
    order = "i.status = 'processed' DESC, i.saved_at DESC, i.id DESC"
    if kind == "items":
        # Saves the user picked: whatever platform is chosen, in their order.
        wanted = [int(i) for i in (target or {}).get("ids") or []][:MAX_PICKED]
        marks = ",".join("?" for _ in wanted)
        found = {int(r["id"]) for r in conn.execute(f"SELECT id FROM items WHERE deleted_at IS NULL AND id IN ({marks})", wanted)}
        return [i for i in wanted if i in found][: limit or MAX_PICKED]
    if kind == "collection":
        sql = (f"SELECT i.id FROM items i JOIN item_collections ic ON ic.item_id = i.id "
               f"WHERE ic.collection_id = ? AND {scope_sql} ORDER BY {order}")
        args: list[Any] = [target.get("id"), *params]  # type: ignore[union-attr]
    elif kind == "tag":
        sql = (f"SELECT i.id FROM items i JOIN item_tags it ON it.item_id = i.id JOIN tags t ON t.id = it.tag_id "
               f"WHERE t.name = ? AND {scope_sql} ORDER BY {order}")
        args = [str(target.get("name") or "").lower(), *params]  # type: ignore[union-attr]
    elif kind == "plan":
        sql = (f"SELECT i.id FROM items i JOIN plan_items pi ON pi.item_id = i.id "
               f"WHERE pi.plan_id = ? AND {scope_sql} ORDER BY pi.position, pi.added_at")
        args = [target.get("id"), *params]  # type: ignore[union-attr]
    else:
        sql = f"SELECT i.id FROM items i WHERE {scope_sql} ORDER BY {order}"
        args = params
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [int(row["id"]) for row in conn.execute(sql, args)]


# ---------- chats in the database ----------


def _chat_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        target = json.loads(row["target_json"]) if row["target_json"] else None
    except json.JSONDecodeError:
        target = None
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "tool": row["tool"],
        "target": target,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_chats(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.chat_id = c.id) AS messages,
                  (SELECT content FROM chat_messages m WHERE m.chat_id = c.id ORDER BY m.id DESC LIMIT 1) AS last
           FROM chats c ORDER BY c.updated_at DESC, c.id DESC"""
    ).fetchall()
    return [
        _chat_row(row) | {"messages": int(row["messages"]), "preview": (row["last"] or "")[:120]}
        for row in rows
    ]


def get_chat(conn: sqlite3.Connection, chat_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if row is None:
        return None
    chat = _chat_row(row)
    chat["target_name"] = target_name(conn, chat["target"])
    chat["messages"] = [
        {
            "id": int(m["id"]),
            "role": m["role"],
            "content": m["content"],
            "found": bool(m["found"]),
            "sources": json.loads(m["sources_json"]) if m["sources_json"] else [],
            "actions": _public_actions(m["actions_json"]),
            "created_at": m["created_at"],
        }
        for m in conn.execute("SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY id", (chat_id,))
    ]
    return chat


def create_chat(conn: sqlite3.Connection, tool: str = "ask", target: dict[str, Any] | None = None,
                title: str | None = None) -> int:
    if tool not in TOOLS:
        raise ValueError("Unknown AI tool.")
    if not title:
        title = TOOL_LABELS[tool] if tool != "ask" else "New chat"
        if target and target.get("type") == "items":
            title = f"{TOOL_LABELS[tool] if tool != 'ask' else 'About'}: {target_name(conn, target).removeprefix('the ')}"
        elif tool != "ask" and target and target.get("type") != "all":
            title = f"{TOOL_LABELS[tool]}: {target_name(conn, target).removeprefix('my ')}"
    return int(conn.execute(
        "INSERT INTO chats (title, tool, target_json) VALUES (?, ?, ?)",
        (title[:80], tool, json.dumps(target) if target else None),
    ).lastrowid or 0)


def rename_chat(conn: sqlite3.Connection, chat_id: int, title: str) -> None:
    title = " ".join(title.split())[:80]
    if not title:
        raise ValueError("A chat needs a name.")
    conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))


def delete_chat(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def _public_actions(raw: str | None) -> dict[str, Any] | None:
    """What the screen shows of the AI's actions (not its working notes)."""
    if not raw:
        return None
    data = json.loads(raw)
    return {"state": data.get("state"), "pending": data.get("pending", []), "changed": data.get("changed", [])}


def _add_message(conn: sqlite3.Connection, chat_id: int, role: str, content: str,
                 sources: list[dict[str, Any]] | None = None, found: bool = True,
                 actions: dict[str, Any] | None = None) -> int:
    message_id = int(conn.execute(
        "INSERT INTO chat_messages (chat_id, role, content, sources_json, found, actions_json) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, role, content, json.dumps(sources) if sources is not None else None, int(found),
         json.dumps(actions) if actions is not None else None),
    ).lastrowid or 0)
    conn.execute("UPDATE chats SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?", (chat_id,))
    return message_id


# ---------- answering ----------


def _messages(tool: str, history: list[Message], sources_text: str, about: str, overview: str = "") -> list[Message]:
    turns = [m for m in history if m.get("role") in ("user", "assistant")][-HISTORY_TURNS:]
    earlier, question = turns[:-1], (turns[-1]["content"] if turns else "")
    parts = []
    if overview:
        parts.append(f"The user's library, in short:\n{overview}")
    if earlier:
        parts.append("Conversation so far:\n" + "\n".join(f"{m['role']}: {m['content'][:800]}" for m in earlier))
    parts.append(f"The saves you may use ({about}):\n\n{sources_text}")
    parts.append(f"Task: {TOOL_INSTRUCTIONS[tool]}")
    parts.append(f"The user says: {question}")
    parts.append('Answer as JSON: {"found": true or false, "answer": "...", "sources": [numbers of the saves you used]}')
    return [{"role": "system", "content": BASE_RULES}, {"role": "user", "content": "\n\n".join(parts)}]


def answer(db: Database, search: SearchService, ai: AIService, chat: dict[str, Any], history: list[Message],
           platform: str | None) -> dict[str, Any]:
    tool, target = chat["tool"], chat.get("target")
    picked = bool(target) and target.get("type") == "items"
    with db.connect() as conn:
        about = target_name(conn, target)
        group = target_items(conn, target, platform) if (tool != "ask" or target) else None
    if tool == "ask" and not picked:
        query = retrieval_query(history)
        hits = search.hybrid(query, limit=SEARCH_POOL) if query else []
        allowed = set(group) if group is not None else None
        if platform and allowed is None:
            with db.connect() as conn:
                allowed = {int(r["id"]) for r in conn.execute("SELECT id FROM items WHERE platform = ?", (platform,))}
        with db.connect() as conn:
            live = {int(r["id"]) for r in conn.execute("SELECT id FROM items WHERE deleted_at IS NULL")}
        hits = [h for h in hits if h.item_id in live]
        hits = [h for h in hits if allowed is None or h.item_id in allowed][:MAX_ASK_SOURCES]
    else:
        # A group (or saves the user picked): the AI reads them all, whatever is asked.
        hits = [HybridHit(item_id, 0.0) for item_id in (group or [])[: MAX_PICKED if picked else MAX_GROUP_SOURCES]]
    if not hits:
        empty = NOTHING_FOUND if tool == "ask" and not picked else (
            f"There are no saves in {about} yet, so there's nothing to work with."
        )
        return {"found": False, "answer": empty, "sources": []}
    ai.check_ready()
    # Few saves: read much more of each transcript.
    per_save = max(1500, min(6000, TRANSCRIPT_BUDGET // len(hits)))
    with db.connect() as conn:
        sources = [describe_source(conn, number, hit, per_save) for number, hit in enumerate(hits, start=1)]
        overview = library_overview(conn, platform)
    reply = ai.chat_json(
        _messages(tool, history, "\n\n".join(s.text for s in sources), about, overview), ChatAnswer
    )
    numbers = cited_numbers(reply, len(sources))
    found = bool(reply.found and reply.answer.strip())
    text = reply.answer.strip() or NOTHING_FOUND
    return {
        "found": found,
        "answer": text,
        "sources": [{"number": n, "item_id": sources[n - 1].item_id} for n in numbers] if found else [],
    }


def _agent_message(conn: sqlite3.Connection, chat_id: int, result: dict[str, Any]) -> None:
    if result["mode"] == "waiting":
        actions = {"state": "waiting", "pending": result["pending"], "rounds": result["state"]["rounds"],
                   "changed": result["state"]["changed"]}
    else:
        actions = {"state": "done", "pending": [], "changed": result.get("changed", []),
                   "rounds": result.get("rounds", [])[-30:]}  # kept to see what the AI did
    _add_message(conn, chat_id, "assistant", result["say"], [], True, actions)


def _agent_label(content: str) -> str:
    words = " ".join(content.split())
    return "AI: " + (words[:40] + "…" if len(words) > 40 else words)


def confirm(db: Database, ai: AIService, chat_id: int, message_id: int, go: bool, agent_tools: Any) -> dict[str, Any]:
    """The user pressed "Do it" (go) or "Cancel" on the AI's waiting changes."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)).fetchone()
        if row is None or not row["actions_json"]:
            raise KeyError("That message doesn't exist any more.")
        data = json.loads(row["actions_json"])
        if data.get("state") != "waiting":
            raise ValueError("That was already answered.")
        chat = get_chat(conn, chat_id) or {}
    if not go:
        with db.connect() as conn:
            data["state"] = "cancelled"
            conn.execute("UPDATE chat_messages SET actions_json = ? WHERE id = ?", (json.dumps(data), message_id))
            _add_message(conn, chat_id, "assistant", "OK, I left everything as it was.", [], True)
            return get_chat(conn, chat_id) or {}
    question = next((m["content"] for m in reversed(chat["messages"]) if m["role"] == "user" and m["id"] < message_id), "")
    history: list[Message] = [{"role": m["role"], "content": m["content"]} for m in chat["messages"] if m["id"] < message_id]
    state = {"rounds": data.get("rounds", []), "changed": list(data.get("changed", []))}
    step = agent_tools.new_step()
    try:
        agent.run_approved(agent_tools.call, agent_tools.actions, data["pending"], state, step)
        with db.connect() as conn:
            data["state"] = "done"
            data["changed"] = state["changed"]
            conn.execute("UPDATE chat_messages SET actions_json = ? WHERE id = ?", (json.dumps(data), message_id))
        try:
            with db.connect() as conn:
                library = agent.library_data(conn)
            result = agent.run(ai.chat_json, agent_tools.call, agent_tools.actions, library, history, state, step)
            if result["mode"] == "answer":
                result = {"mode": "done", "say": agent._summary(state["changed"]), "changed": state["changed"]}
        except Exception:  # noqa: BLE001 - the changes are made; only the follow-up failed
            result = {"mode": "done", "say": agent._summary(state["changed"]), "changed": state["changed"]}
        # The waiting message lists what was approved; this one only what came after.
        result["changed"] = result.get("changed", [])[len(data["changed"]):]
    finally:
        agent_tools.finish(step, _agent_label(question))
    with db.connect() as conn:
        _agent_message(conn, chat_id, result)
        return get_chat(conn, chat_id) or {}


def send(db: Database, search: SearchService, ai: AIService, chat_id: int, content: str,
         platform: str | None, agent_tools: Any = None) -> dict[str, Any]:
    """Add the user's message, answer it, keep both. If the AI fails, the
    user's message is taken back out so the chat stays tidy (they can retry)."""
    with db.connect() as conn:
        chat = get_chat(conn, chat_id)
        if chat is None:
            raise KeyError("That chat doesn't exist any more.")
        user_id = _add_message(conn, chat_id, "user", content)
        if chat["title"] == "New chat":
            conn.execute("UPDATE chats SET title = ? WHERE id = ?", (" ".join(content.split())[:60], chat_id))
    history: list[Message] = [{"role": m["role"], "content": m["content"]} for m in chat["messages"]]
    history.append({"role": "user", "content": content})
    # In a plain "Ask anything" chat the AI can also do things in the app.
    if agent_tools is not None and chat["tool"] == "ask" and not chat.get("target"):
        step = agent_tools.new_step()
        try:
            ai.check_ready()
            with db.connect() as conn:
                library = agent.library_data(conn)
            result = agent.run(ai.chat_json, agent_tools.call, agent_tools.actions, library, history, {}, step)
        except Exception:
            with db.connect() as conn:
                conn.execute("DELETE FROM chat_messages WHERE id = ?", (user_id,))
            raise
        finally:
            agent_tools.finish(step, _agent_label(content))
        if result["mode"] != "answer":
            with db.connect() as conn:
                _agent_message(conn, chat_id, result)
                return get_chat(conn, chat_id) or {}
    try:
        reply = answer(db, search, ai, chat, history, platform)
    except Exception:
        with db.connect() as conn:
            conn.execute("DELETE FROM chat_messages WHERE id = ?", (user_id,))
        raise
    with db.connect() as conn:
        _add_message(conn, chat_id, "assistant", reply["answer"], reply["sources"], reply["found"])
        return get_chat(conn, chat_id) or {}
