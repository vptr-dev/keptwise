"""SearchService: keyword + similar-meaning search, and the job that keeps
the similar-meaning index up to date.

- Keyword search always works (SQLite FTS5, updated by triggers).
- Similar search needs the small fastembed model and the "search_index"
  background job, which turns each item's passages into vectors. The job
  starts by itself after transcripts or AI notes are made, and at start-up.
- hybrid() merges both lists (reciprocal rank fusion): an item found both
  ways rises to the top.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.db.connection import Database
from app.enrich.download import DownloadError
from app.jobs.repo import FINISHED, JobsRepo
from app.jobs.runner import Handler, JobContext, JobRunner
from app.search.embedder import APPROX_BYTES, Embedder, FastEmbedder, download_search_model, find_model
from app.search.keyword import KeywordHit, keyword_search
from app.search.passages import make_passages, text_hash

JOB_KIND = "search_index"
BATCH = 16
# Similar results below this cosine similarity are left out. Measured on
# bge-small with the user's saves: unrelated text scored up to about 0.55,
# related text 0.59-0.75. Results also have to be close to the best one.
MIN_SIMILARITY = 0.56
NEAR_BEST = 0.08
RRF_K = 60


@dataclass
class SimilarHit:
    item_id: int
    score: float
    part: str
    start_char: int
    text: str
    part_length: int = 0


@dataclass
class HybridHit:
    item_id: int
    score: float
    keyword: KeywordHit | None = None
    similar: SimilarHit | None = None
    sources: list[str] = field(default_factory=list)  # "words", "similar"


class _Vectors:
    """All passage vectors in memory, reloaded when the table changes."""

    def __init__(self) -> None:
        self.key: tuple[int, int] | None = None
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self.rows: list[tuple[int, str, int, str]] = []  # item_id, part, start_char, text


class SearchService:
    def __init__(
        self,
        db: Database,
        models_root: Path,
        runner: JobRunner,
        jobs: JobsRepo,
        embedder: Embedder | None = None,
        downloader: Callable[..., Path] = download_search_model,
    ) -> None:
        self.db = db
        self.models_root = models_root
        self.runner = runner
        self.jobs = jobs
        self._embedder = embedder
        self._downloader = downloader
        self._vectors = _Vectors()
        self._lock = threading.Lock()
        runner.register(JOB_KIND, self._run_index)

    # ---------- the model ----------

    def model_ready(self) -> bool:
        return self._embedder is not None or find_model(self.models_root) is not None

    def forget_model(self) -> None:
        """Let go of the loaded model, so its files can be deleted."""
        with self._lock:
            self._embedder = None

    def embedder(self) -> Embedder | None:
        with self._lock:
            if self._embedder is None:
                folder = find_model(self.models_root)
                if folder is not None:
                    self._embedder = FastEmbedder(folder)
            return self._embedder

    # ---------- what still needs indexing ----------

    def _model_name(self) -> str:
        emb = self.embedder()
        return emb.name if emb else ""

    def _stale(self, conn: sqlite3.Connection, model: str) -> tuple[list[tuple[int, dict[str, str], str]], int]:
        """Items whose text changed since they were indexed, and how many have any text."""
        done = {
            int(row["item_id"]): (row["model"], row["text_hash"])
            for row in conn.execute("SELECT item_id, model, text_hash FROM search_indexed")
        }
        todo = []
        with_text = 0
        for row in conn.execute("SELECT rowid, about, transcript, notes FROM search_fts ORDER BY rowid DESC"):
            parts = {"about": row["about"] or "", "transcript": row["transcript"] or "", "notes": row["notes"] or ""}
            has_text = any(value.strip() for value in parts.values())
            with_text += has_text
            digest = text_hash(parts)
            item_id = int(row["rowid"])
            if done.get(item_id) != (model, digest) and (has_text or item_id in done):
                todo.append((item_id, parts, digest))
        return todo, with_text

    def status(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            todo, with_text = self._stale(conn, self._model_name() if self.model_ready() else "?")
        job = self._active_job()
        return {
            "model_ready": self.model_ready(),
            "model_bytes": APPROX_BYTES,
            "items_with_text": with_text,
            "waiting": len(todo),
            "job": job,
        }

    def _active_job(self) -> dict[str, Any] | None:
        for job in self.jobs.recent(20):
            if job["kind"] == JOB_KIND and job["status"] not in FINISHED and job["status"] != "interrupted":
                return job
        return None

    def ensure_index(self, allow_download: bool = False) -> int | None:
        """Start the index job if something is waiting. Returns the job id."""
        active = self._active_job()
        if active:
            return int(active["id"])
        if not self.model_ready() and not allow_download:
            return None
        if self.model_ready():
            with self.db.connect() as conn:
                todo, _ = self._stale(conn, self._model_name())
            if not todo:
                return None
        return self.runner.submit(JOB_KIND, "Getting videos ready for similar search", {})

    def after(self, handler: Handler) -> Handler:
        """Wrap a job handler so the index catches up when that job ends."""

        def run(ctx: JobContext) -> dict[str, Any] | None:
            try:
                return handler(ctx)
            finally:
                try:
                    self.ensure_index()
                except Exception:  # noqa: BLE001 - never spoil the job that just ran
                    pass

        return run

    # ---------- the index job ----------

    def _run_index(self, ctx: JobContext) -> dict[str, Any]:
        if not self.model_ready():
            ctx.progress(0, APPROX_BYTES, "Downloading the search model (about 67 MB, only once)…", force=True)

            def report(done: int, total: int) -> None:
                ctx.progress(done, total, f"Downloading the search model: {done / 1e6:.0f} of {total / 1e6:.0f} MB")

            try:
                self._downloader(self.models_root, report=report, check=ctx.check)
            except DownloadError as error:
                raise RuntimeError(str(error)) from error
        embedder = self.embedder()
        assert embedder is not None
        with self.db.connect() as conn:
            todo, _ = self._stale(conn, embedder.name)
        total = len(todo)
        ctx.progress(0, total, f"Reading {total} videos for similar search…", force=True)
        failed = 0
        for start in range(0, total, BATCH):
            ctx.check()
            for item_id, parts, digest in todo[start : start + BATCH]:
                try:
                    self._index_one(embedder, item_id, parts, digest)
                except Exception:  # noqa: BLE001 - one item never stops the batch
                    failed += 1
            done = min(start + BATCH, total)
            ctx.progress(done, total, f"Ready for similar search: {done} of {total}")
        message = f"{total - failed} videos ready for similar search"
        if failed:
            message += f", {failed} couldn't be read"
        return {"message": message, "indexed": total - failed, "failed": failed}

    def _index_one(self, embedder: Embedder, item_id: int, parts: dict[str, str], digest: str) -> None:
        passages = make_passages(parts)
        vectors = embedder.embed_passages([p.text for p in passages]) if passages else None
        with self.db.connect() as conn:
            conn.execute("DELETE FROM search_passages WHERE item_id = ?", (item_id,))
            for number, passage in enumerate(passages):
                assert vectors is not None
                conn.execute(
                    "INSERT INTO search_passages (item_id, part, start_char, text, vector) VALUES (?, ?, ?, ?, ?)",
                    (item_id, passage.part, passage.start_char, passage.text,
                     np.asarray(vectors[number], dtype=np.float32).tobytes()),
                )
            conn.execute(
                """INSERT INTO search_indexed (item_id, model, text_hash) VALUES (?, ?, ?)
                   ON CONFLICT (item_id) DO UPDATE SET model = excluded.model, text_hash = excluded.text_hash,
                     indexed_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
                (item_id, embedder.name, digest),
            )

    # ---------- searching ----------

    def _load_vectors(self, conn: sqlite3.Connection) -> _Vectors:
        key_row = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM search_passages").fetchone()
        key = (int(key_row[0]), int(key_row[1]))
        with self._lock:
            if self._vectors.key != key:
                fresh = _Vectors()
                rows = conn.execute("SELECT item_id, part, start_char, text, vector FROM search_passages").fetchall()
                fresh.rows = [(int(r["item_id"]), r["part"], int(r["start_char"]), r["text"]) for r in rows]
                fresh.matrix = (
                    np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
                    if rows else np.zeros((0, 0), dtype=np.float32)
                )
                fresh.key = key
                self._vectors = fresh
            return self._vectors

    def similar(self, query: str, limit: int = 30, min_score: float = MIN_SIMILARITY,
                near_best: float = NEAR_BEST) -> list[SimilarHit]:
        """The items with a passage closest in meaning to the query (best passage each)."""
        embedder = self.embedder()
        if embedder is None or not query.strip():
            return []
        with self.db.connect() as conn:
            vectors = self._load_vectors(conn)
            if not vectors.rows:
                return []
            scores = vectors.matrix @ embedder.embed_query(query.strip())
            if len(scores):
                min_score = max(min_score, float(scores.max()) - near_best)
            best: dict[int, SimilarHit] = {}
            for index in np.argsort(-scores):
                score = float(scores[index])
                if score < min_score or len(best) >= limit:
                    break
                item_id, part, start_char, text = vectors.rows[index]
                if item_id not in best:
                    best[item_id] = SimilarHit(item_id, score, part, start_char, text)
            if best:
                marks = ",".join("?" for _ in best)
                lengths = conn.execute(
                    f"SELECT rowid, length(about) AS a, length(transcript) AS t, length(notes) AS n "
                    f"FROM search_fts WHERE rowid IN ({marks})", list(best)
                ).fetchall()
                for row in lengths:
                    hit = best[int(row["rowid"])]
                    hit.part_length = int({"about": row["a"], "transcript": row["t"], "notes": row["n"]}[hit.part] or 0)
        return list(best.values())

    def hybrid(self, query: str, limit: int = 30) -> list[HybridHit]:
        with self.db.connect() as conn:
            words = keyword_search(conn, query, limit=limit)
        similar = self.similar(query, limit=limit)
        merged: dict[int, HybridHit] = {}
        for rank, hit in enumerate(words):
            entry = merged.setdefault(hit.item_id, HybridHit(hit.item_id, 0.0))
            entry.keyword = hit
            entry.score += 1.0 / (RRF_K + rank)
            entry.sources.append("words")
        for rank, sim in enumerate(similar):
            entry = merged.setdefault(sim.item_id, HybridHit(sim.item_id, 0.0))
            entry.similar = sim
            entry.score += 1.0 / (RRF_K + rank)
            entry.sources.append("similar")
        return sorted(merged.values(), key=lambda h: -h.score)[:limit]
