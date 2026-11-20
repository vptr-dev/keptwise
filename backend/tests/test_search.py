"""Tests for search (keywords, similar meaning, both together), the index
job, the search model download, and chat over the saves.

A tiny fake embedder stands in for fastembed: it turns words into numbers
and knows a few made-up synonyms, so "spaghetti" means the same as "pasta".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.secrets import MemoryKeyStore
from app.api.session import TOKEN_HEADER
from app.db.items_repo import NewItem, save_transcript, update_item, upsert_item
from app.main import create_app
from app.search.chat import ChatAnswer, cited_numbers, retrieval_query
from app.search.embedder import REPO, WANTED_FILES, download_search_model, find_model, normalize
from app.search.keyword import fts_query, keyword_search, split_marks
from app.search.passages import make_passages, split_transcript
from app.search.service import JOB_KIND
from app.services import AppServices, build_services
from tests.conftest import TOKEN
from tests.fakes import FakeNet
from tests.test_enrich import FakeServer, tree_for
from tests.test_jobs import wait_for_status

OLLAMA = "http://localhost:11434"
SYNONYMS = {"spaghetti": "pasta", "noodles": "pasta", "workout": "gym", "exercise": "gym"}


class FakeEmbedder:
    name = "fake-words"

    def _one(self, text: str) -> np.ndarray:
        vector = np.zeros(64, dtype=np.float32)
        for word in text.lower().split():
            word = SYNONYMS.get(word.strip(".,!?"), word.strip(".,!?"))
            if len(word) > 2:
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
        return vector

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        return normalize(np.vstack([self._one(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return normalize(self._one(text))[0]


@pytest.fixture
def ssvc(isolated_data_dir: Path, net: FakeNet) -> Iterator[AppServices]:
    """Services with the fake embedder, so similar search works."""
    services = build_services(isolated_data_dir, keys=MemoryKeyStore(), http=net.client(), embedder=FakeEmbedder())
    services.runner.start()
    yield services
    services.shutdown()


@pytest.fixture
def sapi(ssvc: AppServices, static_dir: Path) -> TestClient:
    app = create_app(session_token=TOKEN, static_dir=static_dir, app_services=ssvc)
    return TestClient(app, headers={TOKEN_HEADER: TOKEN})


def add(svc: AppServices, n: int, caption: str, transcript: str | None = None, duration: float | None = None,
        summary: str | None = None) -> int:
    with svc.db.connect() as conn:
        item_id, _ = upsert_item(conn, NewItem("tiktok", f"https://www.tiktok.com/@x/video/{n}", caption=caption))
        if duration:
            update_item(conn, item_id, duration_s=duration)
        if transcript is not None:
            save_transcript(conn, item_id, transcript, "en", "whisper-small")
        if summary:
            conn.execute(
                "INSERT INTO ai_results (item_id, title, summary, steps_json, tags) VALUES (?, ?, ?, ?, ?)",
                (item_id, f"Notes {n}", summary, json.dumps([{"text": "Buy fresh basil", "done": False}]),
                 json.dumps(["dinner"])),
            )
    return item_id


def index_all(svc: AppServices) -> None:
    job_id = svc.search.ensure_index()
    assert job_id is not None
    wait_for_status(svc, job_id, "done")


# ---------- keyword search ----------


def test_fts_query_is_safe_and_matches_word_starts() -> None:
    assert fts_query("Pasta  recipes!") == '"pasta" AND "recipes"*'
    assert fts_query('" ( NEAR') == '"near"*'
    assert fts_query("go") == '"go"'  # too short to match as a start
    assert fts_query("pasta sauce", any_word=True) == '"pasta" OR "sauce"*'
    assert fts_query("  ?! ") is None
    # Little filler words are left out, unless that's all there is.
    assert fts_query("how to revise for exams") == '"revise" AND "exams"*'
    assert fts_query("to be") == '"to" AND "be"'


def test_split_marks() -> None:
    segments = split_marks("boil the \x02pasta\x03 now")
    assert [(s.text, s.hit) for s in segments] == [("boil the ", False), ("pasta", True), (" now", False)]


def test_keyword_search_finds_words_in_every_part(svc: AppServices) -> None:
    pasta = add(svc, 1, "Easy dinner", "First boil the water, then add the pasta and salt.", summary="Quick carbonara")
    add(svc, 2, "Paris in springtime", "Blossom everywhere")
    with svc.db.connect() as conn:
        hits = keyword_search(conn, "pasta")
        assert [h.item_id for h in hits] == [pasta]
        transcript = next(f for f in hits[0].fields if f.part == "transcript")
        assert any(s.hit and s.text.lower() == "pasta" for s in transcript.segments)
        assert transcript.start_char == 0 and transcript.part_length > 0
        assert hits[0].words == ["pasta"]
        # Stemming: "boiling" finds "boil". Notes (steps and tags) are searched too.
        assert [h.item_id for h in keyword_search(conn, "boiling")] == [pasta]
        assert [h.item_id for h in keyword_search(conn, "basil")] == [pasta]
        assert {f.part for f in keyword_search(conn, "carbonara")[0].fields} == {"notes"}
        # Words from the JSON itself are never found.
        assert keyword_search(conn, "text") == [] and keyword_search(conn, "false") == []
        # Typing: the last word matches as a start.
        assert [h.item_id for h in keyword_search(conn, "spring")] == [2]


def test_keyword_search_falls_back_to_any_word(svc: AppServices) -> None:
    add(svc, 1, "pasta night")
    add(svc, 2, "pasta and sauce")
    with svc.db.connect() as conn:
        assert [h.item_id for h in keyword_search(conn, "pasta sauce")] == [2]
        assert {h.item_id for h in keyword_search(conn, "pasta lasagne")} == {1, 2}
        assert keyword_search(conn, "lasagne") == []


def test_the_index_follows_changes(svc: AppServices) -> None:
    item_id = add(svc, 1, "one")
    with svc.db.connect() as conn:
        save_transcript(conn, item_id, "kayak trip", "en", "whisper")
        assert keyword_search(conn, "kayak")
        save_transcript(conn, item_id, "bike trip", "en", "whisper")
        assert not keyword_search(conn, "kayak") and keyword_search(conn, "bike")
        update_item(conn, item_id, title="Mountain ride")
        assert keyword_search(conn, "mountain")
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        assert not keyword_search(conn, "bike")


# ---------- passages ----------


def test_transcripts_are_cut_into_overlapping_passages() -> None:
    text = " ".join(f"w{i}" for i in range(150))
    passages = split_transcript(text)
    assert len(passages) == 3
    assert passages[0].text.startswith("w0 ") and passages[0].text.endswith(" w69")
    assert passages[1].text.startswith("w55 ")  # 15 words overlap
    assert text[passages[1].start_char :].startswith("w55")
    assert passages[-1].text.endswith("w149")
    assert split_transcript("   ") == []
    parts = make_passages({"about": "A title", "transcript": "short one", "notes": ""})
    assert [p.part for p in parts] == ["about", "transcript"]


# ---------- similar search and the index job ----------


def test_index_job_and_similar_search(ssvc: AppServices) -> None:
    pasta = add(ssvc, 1, "Dinner idea", "Cook the pasta for ten minutes then add cheese")
    gym = add(ssvc, 2, "Leg day", "Squats and lunges at the gym")
    add(ssvc, 3, "")  # no text: nothing to index
    assert ssvc.search.status()["waiting"] == 2
    index_all(ssvc)
    status = ssvc.search.status()
    assert status["waiting"] == 0 and status["items_with_text"] == 2 and status["model_ready"]
    assert ssvc.search.ensure_index() is None  # nothing left to do

    hits = ssvc.search.similar("spaghetti", min_score=0.2)
    assert hits[0].item_id == pasta and hits[0].part == "transcript"
    assert ssvc.search.similar("exercise", min_score=0.2)[0].item_id == gym

    # Changed text gets indexed again.
    with ssvc.db.connect() as conn:
        save_transcript(conn, gym, "Rowing machine intervals", "en", "whisper")
    assert ssvc.search.status()["waiting"] == 1
    index_all(ssvc)
    with ssvc.db.connect() as conn:
        texts = [r[0] for r in conn.execute("SELECT text FROM search_passages WHERE item_id = ?", (gym,))]
    assert "Rowing machine intervals" in texts and not any("Squats" in t for t in texts)


def test_hybrid_puts_items_found_both_ways_first(ssvc: AppServices) -> None:
    both = add(ssvc, 1, "pasta", "pasta")
    only_meaning = add(ssvc, 2, "noodles", "noodles")
    add(ssvc, 3, "gym", "squats")
    index_all(ssvc)
    hits = ssvc.search.hybrid("pasta")
    assert [h.item_id for h in hits] == [both, only_meaning]
    assert set(hits[0].sources) == {"words", "similar"} and hits[1].sources == ["similar"]


def test_finishing_a_transcripts_job_updates_the_index(ssvc: AppServices) -> None:
    add(ssvc, 1, "pasta", "pasta")
    calls: list[str] = []
    wrapped = ssvc.search.after(lambda ctx: calls.append("ran") or {"message": "ok"})
    ssvc.runner.register("pretend", wrapped)
    job_id = ssvc.runner.submit("pretend", "Pretend transcripts", {})
    wait_for_status(ssvc, job_id, "done")
    index_jobs = [j for j in ssvc.jobs.recent(10) if j["kind"] == JOB_KIND]
    assert calls == ["ran"] and index_jobs
    wait_for_status(ssvc, index_jobs[0]["id"], "done")


def test_without_the_model_only_keywords_work(svc: AppServices) -> None:
    add(svc, 1, "pasta", "pasta")
    assert not svc.search.model_ready()
    assert svc.search.ensure_index() is None  # never downloads by itself
    assert svc.search.similar("pasta") == []
    assert [h.sources for h in svc.search.hybrid("pasta")] == [["words"]]


def test_search_model_download(tmp_path: Path) -> None:
    files = {name: b"x" * (10 + i) for i, name in enumerate(WANTED_FILES)}
    hub = "https://huggingface.co"
    server = FakeServer({
        f"{hub}/api/models/{REPO}/tree/main": tree_for({**files, "README.md": b"hi"}),
        **{f"{hub}/{REPO}/resolve/main/{name}": body for name, body in files.items()},
    })
    progress: list[tuple[int, int]] = []
    assert find_model(tmp_path) is None
    folder = download_search_model(tmp_path, report=lambda d, t: progress.append((d, t)), opener=server)
    assert find_model(tmp_path) == folder
    assert progress[-1][0] == progress[-1][1] == sum(map(len, files.values()))
    assert not any("README" in url for url, _ in server.requests)


# ---------- routes ----------


def test_search_route_shows_matches_and_where(sapi: TestClient, ssvc: AppServices) -> None:
    words = " ".join(["talk"] * 90 + ["pasta"] + ["talk"] * 9)
    item_id = add(ssvc, 1, "Long video", words, duration=100)
    index_all(ssvc)
    data = sapi.get("/api/search", params={"q": "pasta"}).json()
    assert data["similar_ready"] is True
    result = data["results"][0]
    assert result["item"]["id"] == item_id and "words" in result["found_by"]
    assert result["words"] == ["pasta"]
    match = result["matches"][0]
    assert match["label"] == "Transcript" and 60 < match["at_seconds"] < 100
    assert any(seg["hit"] for seg in match["segments"])
    assert sapi.get("/api/search", params={"q": " "}).json()["results"] == []
    only_words = sapi.get("/api/search", params={"q": "pasta", "mode": "words"}).json()["results"]
    assert all("words" in r["found_by"] for r in only_words)


def test_caption_only_search(sapi: TestClient, ssvc: AppServices) -> None:
    in_caption = add(ssvc, 1, "Pasta night", "boil the water first")
    add(ssvc, 2, "Dinner ideas", "this pasta is quick")
    index_all(ssvc)
    results = sapi.get("/api/search", params={"q": "pasta", "mode": "captions"}).json()["results"]
    assert [r["item"]["id"] for r in results] == [in_caption]
    assert [m["label"] for m in results[0]["matches"]] == ["Caption"]
    assert results[0]["similar"] is None


def test_item_details_and_status_routes(sapi: TestClient, ssvc: AppServices) -> None:
    item_id = add(ssvc, 1, "pasta", "boil water")
    details = sapi.get(f"/api/items/{item_id}").json()
    assert details["transcript"] == "boil water" and details["item"]["id"] == item_id
    assert sapi.get("/api/items/999").status_code == 404
    status = sapi.get("/api/search/status").json()
    assert status["model_ready"] is True
    assert sapi.post("/api/search/index").status_code == 200


# ---------- chat ----------


def test_retrieval_query_adds_the_previous_question_to_short_follow_ups() -> None:
    history = [
        {"role": "user", "content": "what pasta recipes did I save?"},
        {"role": "assistant", "content": "Two [1][2]"},
        {"role": "user", "content": "the second one?"},
    ]
    assert retrieval_query(history) == "what pasta recipes did I save? the second one?"
    assert retrieval_query(history[:1]) == "what pasta recipes did I save?"


def test_cited_numbers_are_checked() -> None:
    answer = ChatAnswer(found=True, answer="Try [2] and [9], or [1].", sources=[2, 7])
    assert cited_numbers(answer, 3) == [2, 1]


@pytest.fixture
def ollama(net: FakeNet) -> FakeNet:
    net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": "gemma4:12b"}]})
    return net


def test_chat_answers_from_the_saves_and_cites_them(sapi: TestClient, ssvc: AppServices, ollama: FakeNet) -> None:
    pasta = add(ssvc, 1, "Carbonara", "eggs, cheese and pasta", summary="A quick carbonara")
    add(ssvc, 2, "Gym", "squats")
    seen: list[str] = []

    def reply(payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        seen.append(" ".join(m["content"] for m in payload["messages"]))
        answer = {"found": True, "answer": "You saved a carbonara [1].", "sources": [1]}
        return {"message": {"content": json.dumps(answer)}}

    ollama.on("POST", f"{OLLAMA}/api/chat", reply)
    data = sapi.post("/api/chat", json={"messages": [{"role": "user", "content": "what pasta recipes did I save?"}]}).json()
    assert data["found"] is True and "[1]" in data["answer"]
    assert [s["item"]["id"] for s in data["sources"]] == [pasta]
    assert "[1] Notes 1" in seen[0] and "eggs, cheese and pasta" in seen[0]
    assert "Gym" not in seen[0]  # only matching saves are sent


def test_chat_says_so_when_nothing_matches(sapi: TestClient, ssvc: AppServices, net: FakeNet) -> None:
    add(ssvc, 1, "Gym", "squats")
    data = sapi.post("/api/chat", json={"messages": [{"role": "user", "content": "zebra migration"}]}).json()
    assert data["found"] is False and data["sources"] == [] and "couldn't find" in data["answer"]
    assert not net.requests  # the AI wasn't even asked


def test_chat_when_the_ai_says_the_saves_dont_cover_it(sapi: TestClient, ssvc: AppServices, ollama: FakeNet) -> None:
    add(ssvc, 1, "pasta", "pasta")
    ollama.on("POST", f"{OLLAMA}/api/chat", {"message": {"content": json.dumps(
        {"found": False, "answer": "Your saves don't say how long to cook it.", "sources": [1]})}})
    data = sapi.post("/api/chat", json={"messages": [{"role": "user", "content": "pasta cooking time"}]}).json()
    assert data["found"] is False and data["sources"] == []


def test_chat_needs_a_question_and_a_ready_ai(sapi: TestClient, ssvc: AppServices, net: FakeNet) -> None:
    assert sapi.post("/api/chat", json={"messages": [{"role": "user", "content": "  "}]}).status_code == 400
    add(ssvc, 1, "pasta", "pasta")
    net.on("GET", f"{OLLAMA}/api/tags", {"models": []})
    response = sapi.post("/api/chat", json={"messages": [{"role": "user", "content": "pasta"}]})
    assert response.status_code == 400 and response.json()["code"] == "model_missing"


# ---------- the AI Assistant ----------


def test_assistant_keeps_chats_and_answers_from_saves(sapi: TestClient, ssvc: AppServices, ollama: FakeNet) -> None:
    pasta = add(ssvc, 1, "Carbonara", "eggs, cheese and pasta", summary="A quick carbonara")
    add(ssvc, 2, "Gym", "squats")
    seen: list[str] = []

    def reply(payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        seen.append(" ".join(m["content"] for m in payload["messages"]))
        return {"message": {"content": json.dumps({"found": True, "answer": "A carbonara [1].", "sources": [1]})}}

    ollama.on("POST", f"{OLLAMA}/api/chat", reply)
    chat = sapi.post("/api/assistant/chats", json={}).json()
    assert chat["title"] == "New chat" and chat["tool"] == "ask"
    data = sapi.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "what pasta did I save?"}).json()
    assert data["title"] == "what pasta did I save?"
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
    assert data["messages"][1]["sources"][0]["item"]["id"] == pasta
    again = sapi.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "and how long?"}).json()
    assert len(again["messages"]) == 4 and "Conversation so far" in seen[-1]

    listed = sapi.get("/api/assistant/chats").json()["chats"]
    assert listed[0]["id"] == chat["id"] and listed[0]["messages"] == 4
    assert sapi.patch(f"/api/assistant/chats/{chat['id']}", json={"title": "Pasta"}).json()["title"] == "Pasta"
    assert sapi.delete(f"/api/assistant/chats/{chat['id']}").json()["chats"] == []
    assert sapi.get(f"/api/assistant/chats/{chat['id']}").status_code == 404


def test_assistant_tools_work_on_a_collection(sapi: TestClient, ssvc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import collections

    pasta = add(ssvc, 1, "Carbonara", "eggs, cheese and pasta", summary="A quick carbonara")
    gym = add(ssvc, 2, "Gym", "squats")
    with ssvc.db.connect() as conn:
        food = collections.ensure(conn, "Food")
        collections.add_by_user(conn, pasta, food)
    seen: list[str] = []

    def reply(payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        seen.append(" ".join(m["content"] for m in payload["messages"]))
        return {"message": {"content": json.dumps({"found": True, "answer": "* Eggs [1]", "sources": [1]})}}

    ollama.on("POST", f"{OLLAMA}/api/chat", reply)
    chat = sapi.post("/api/assistant/chats", json={"tool": "shopping", "target": {"type": "collection", "id": food}}).json()
    assert chat["title"] == "Shopping or packing list: Food collection" and chat["target_name"] == "my Food collection"
    data = sapi.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "Make a shopping list"}).json()
    assert "shopping or packing list" in seen[0] and "Carbonara" in seen[0] and "squats" not in seen[0]
    assert data["messages"][1]["sources"][0]["item"]["id"] == pasta

    empty = sapi.post("/api/assistant/chats", json={"tool": "summary", "target": {"type": "tag", "name": "nothing"}}).json()
    answered = sapi.post(f"/api/assistant/chats/{empty['id']}/messages", json={"content": "Summarise"}).json()
    assert answered["messages"][1]["found"] is False and len(seen) == 1  # no AI call for an empty group
    assert gym  # in no collection, never sent
    tools = sapi.get("/api/assistant/tools").json()["tools"]
    assert {tool["id"] for tool in tools} == {"ask", "find", "summary", "plan", "shopping", "compare", "takeaways"}


def test_a_failed_answer_leaves_the_chat_tidy(sapi: TestClient, ssvc: AppServices, net: FakeNet) -> None:
    add(ssvc, 1, "Carbonara", "eggs, cheese and pasta")
    chat = sapi.post("/api/assistant/chats", json={}).json()
    failed = sapi.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "pasta?"})
    assert failed.status_code == 400  # Ollama isn't there
    assert sapi.get(f"/api/assistant/chats/{chat['id']}").json()["messages"] == []


def test_assistant_reads_the_saves_you_picked(sapi: TestClient, ssvc: AppServices, ollama: FakeNet) -> None:
    from app.ai.sorting import collections, tags

    pasta = add(ssvc, 1, "Carbonara", "eggs, cheese and pasta", summary="A quick carbonara")
    gym = add(ssvc, 2, "Gym", "squats and lunges")
    other = add(ssvc, 3, "Paris", "the Louvre")
    with ssvc.db.connect() as conn:
        collections.add_by_user(conn, pasta, collections.ensure(conn, "Food"))
        tags.add(conn, pasta, "dinner")
    seen: list[str] = []

    def reply(payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        seen.append(" ".join(m["content"] for m in payload["messages"]))
        return {"message": {"content": json.dumps({"found": True, "answer": "Pasta first [1], then the gym [2].", "sources": [1, 2]})}}

    ollama.on("POST", f"{OLLAMA}/api/chat", reply)
    chat = sapi.post("/api/assistant/chats", json={"target": {"type": "items", "ids": [pasta, gym]}}).json()
    assert chat["title"] == "About: 2 saves I picked" and chat["target_name"] == "the 2 saves I picked"
    # Any question works: the picked saves are read whether or not they match the words.
    data = sapi.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "Which should I do first?"}).json()
    assert [s["item"]["id"] for s in data["messages"][1]["sources"]] == [pasta, gym]
    sent = seen[0]
    assert "Carbonara" in sent and "squats" in sent and "Louvre" not in sent
    # The AI is told where each save is filed, its tags, and about the library as a whole.
    assert "In the user's collections: Food" in sent and "Tags: dinner" in sent
    assert "The user's library, in short:" in sent and "3 saves in all" in sent
    assert other

    takeaways = sapi.post("/api/assistant/chats", json={"tool": "takeaways", "target": {"type": "items", "ids": [gym]}}).json()
    assert takeaways["title"] == "Key takeaways: save I picked"
    assert sapi.post("/api/assistant/chats", json={"target": {"type": "items", "ids": []}}).status_code == 400
