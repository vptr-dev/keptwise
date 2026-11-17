"""The "enrich" background job: details, thumbnail, sound and transcript.

For each item, in order:
1. Read the public page (title, caption, author, length, thumbnail link).
2. Keep a small copy of the thumbnail.
3. Download the file with the video's sound into <data>\\audio\\.
4. Turn the speech into text on this PC, save it, delete the sound file.

Steps 1-3 for the NEXT item run in a helper thread while this item is being
transcribed, so the network and the processor are both busy.

Every finished item is saved straight away, so Pause, Cancel and app
restarts lose nothing: Resume skips items that are already done, and a
half-downloaded sound file carries on where it stopped.

One bad item never stops the batch: its reason is saved on the item. Only
losing the internet (3 network errors in a row) stops the job, because
then every other item would fail too.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.pictures import capture_frames
from app.db.connection import Database
from app.db.items_repo import get_item_row, get_transcript, save_transcript, update_item
from app.db.settings_repo import SettingsRepo
from app.enrich.errors import plain_reason
from app.enrich.fetch import Fetcher, TooLong, VideoDetails, YtDlpFetcher, forbidden
from app.enrich.priority import background_priority
from app.enrich.speech_models import DEFAULT_MODEL, download_model, is_downloaded, model_folder
from app.enrich.transcribe import NoSound, Transcriber
from app.importers.common import plural
from app.jobs.runner import Handler, JobCancelled, JobContext
from app.paths import AppPaths

MODEL_KEY = "transcription.model"
DEVICE_KEY = "transcription.device"
DEVICES = ("auto", "cpu")
DONE_STATUSES = ("enriched", "processed")
NETWORK_STRIKES = 3
OFFLINE = (
    "Stopped because the internet connection seems to be down. "
    "Press Resume when you're back online; finished videos are kept."
)
# Per-item timings kept in the job's result (the first ones only).
TIMINGS_KEPT = 100

# (model folder, model id, device) -> something with transcribe(), source, close()
TranscriberFactory = Callable[[Path, str, str], Transcriber]

_one_at_a_time = threading.Lock()


@dataclass
class Prepared:
    """What the helper thread fetched for one item. Files only, no database."""

    item: dict[str, Any]
    details: VideoDetails | None = None
    error: BaseException | None = None  # the page couldn't be read
    thumbnail_name: str | None = None
    media_path: Path | None = None
    media_error: BaseException | None = None  # details OK, sound not
    details_s: float = 0.0
    sound_s: float = 0.0


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def leftover_media(audio_dir: Path, item_id: int) -> Path | None:
    """A sound file from an earlier run that finished downloading."""
    for path in sorted(audio_dir.glob(f"{item_id}.*")):
        if not path.name.endswith((".part", ".ytdl")):
            return path
    return None


def prepare(fetcher: Fetcher, paths: AppPaths, item: dict[str, Any], need_media: bool) -> Prepared:
    result = Prepared(item)
    started = time.monotonic()
    try:
        details, handle = fetcher.details(item["url"], item["platform"])
    except Exception as error:  # noqa: BLE001 - saved on the item instead
        result.error = error
        result.details_s = time.monotonic() - started
        return result
    result.details = details
    result.details_s = time.monotonic() - started

    started = time.monotonic()
    thumbnail = paths.thumbnails / f"{item['id']}.jpg"
    if thumbnail.is_file():
        result.thumbnail_name = thumbnail.name
    elif details.thumbnail_url:
        try:
            fetcher.download_thumbnail(details.thumbnail_url, thumbnail)
            result.thumbnail_name = thumbnail.name
        except Exception:  # noqa: BLE001 - a missing picture is fine
            pass
    if need_media:
        result.media_path = leftover_media(paths.audio, item["id"])
        if result.media_path is None:
            try:
                result.media_path = fetcher.download_media(handle, paths.audio, str(item["id"]))
            except Exception as error:  # noqa: BLE001
                result.media_error = error
    result.sound_s = time.monotonic() - started
    return result


def make_enrich_handler(
    db: Database,
    paths: AppPaths,
    settings: SettingsRepo,
    fetcher_factory: Callable[[], Fetcher] = YtDlpFetcher,
    transcriber_factory: TranscriberFactory = Transcriber,
    model_downloader: Callable[..., Path] = download_model,
) -> Handler:
    def run_enrich(ctx: JobContext) -> dict[str, Any]:
        ids = [int(item_id) for item_id in ctx.params.get("item_ids", [])]
        if not _one_at_a_time.acquire(blocking=False):
            ctx.progress(0, len(ids), "Waiting for the other transcripts job to finish…")
            while not _one_at_a_time.acquire(timeout=0.5):
                ctx.check()
        try:
            with background_priority():
                return Enricher(ctx, db, paths, settings, fetcher_factory(), transcriber_factory,
                                model_downloader).run(ids)
        finally:
            _one_at_a_time.release()

    return run_enrich


class Enricher:
    def __init__(
        self,
        ctx: JobContext,
        db: Database,
        paths: AppPaths,
        settings: SettingsRepo,
        fetcher: Fetcher,
        transcriber_factory: TranscriberFactory,
        model_downloader: Callable[..., Path],
    ) -> None:
        self.ctx = ctx
        self.db = db
        self.paths = paths
        self.fetcher = fetcher
        self.model_id = str(settings.get(MODEL_KEY, DEFAULT_MODEL))
        self.device = str(settings.get(DEVICE_KEY, "auto"))
        self.transcriber_factory = transcriber_factory
        self.model_downloader = model_downloader
        self.transcriber: Transcriber | None = None
        self.counts = {"transcribed": 0, "no_speech": 0, "details_only": 0, "failed": 0, "later": 0, "refused": 0}
        self.timings: list[dict[str, Any]] = []

    # ---------- the whole batch ----------

    def run(self, ids: list[int]) -> dict[str, Any]:
        ctx = self.ctx
        total = len(ids)
        todo: list[dict[str, Any]] = []
        with self.db.connect() as conn:
            for item_id in ids:
                row = get_item_row(conn, item_id)
                if row is not None and row["status"] not in DONE_STATUSES:
                    todo.append(row)
        done = total - len(todo)
        ctx.progress(done, total, "Getting ready…")
        if todo:
            self._get_model_ready(done, total)
            self._work(todo, done, total)
        return self._summary(total)

    def _get_model_ready(self, done: int, total: int) -> None:
        if is_downloaded(self.paths.models, self.model_id):
            return

        def report(have: int, size: int) -> None:
            self.ctx.progress(
                done, total,
                f"Downloading the speech-to-text model (first time only): "
                f"{have / 1e6:,.0f} of {size / 1e6:,.0f} MB",
            )

        self.model_downloader(self.paths.models, self.model_id, report=report, check=self.ctx.check)

    def _work(self, todo: list[dict[str, Any]], done: int, total: int) -> None:
        ctx = self.ctx
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="enrich-fetch")
        strikes = 0
        try:
            upcoming = self._submit(executor, todo[0])
            for index in range(len(todo)):
                ctx.progress(done, total, f"Getting video {done + 1:,} of {total:,}…", force=True)
                prepared = self._wait_for(upcoming)
                if index + 1 < len(todo):
                    upcoming = self._submit(executor, todo[index + 1])
                ctx.check()
                ctx.progress(done, total, f"Transcribing video {done + 1:,} of {total:,}…", force=True)
                outcome = self._finish(prepared)
                self.counts[outcome] += 1
                strikes = strikes + 1 if outcome == "later" else 0  # "refused" is TikTok, not the internet
                if strikes >= NETWORK_STRIKES:
                    raise RuntimeError(OFFLINE)
                done += 1
                ctx.progress(done, total, f"Finished {done:,} of {total:,}", force=True)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            if self.transcriber is not None:
                self.transcriber.close()

    def _submit(self, executor: ThreadPoolExecutor, item: dict[str, Any]) -> Future[Prepared]:
        with self.db.connect() as conn:
            need_media = get_transcript(conn, item["id"]) is None
        return executor.submit(prepare, self.fetcher, self.paths, item, need_media)

    def _wait_for(self, future: Future[Prepared]) -> Prepared:
        while True:
            try:
                return future.result(timeout=0.5)
            except FutureTimeout:
                self.ctx.check()  # Pause and Cancel work while waiting too

    # ---------- one item ----------

    def _finish(self, prepared: Prepared) -> str:
        item = prepared.item
        item_id = int(item["id"])
        if prepared.error is not None or prepared.details is None:
            reason = plain_reason(prepared.error or "No details")
            with self.db.connect() as conn:
                if reason.is_network:
                    update_item(conn, item_id, error=reason.text)  # stays waiting; try later
                    return "later"
                update_item(conn, item_id, status="failed", error=reason.text,
                            enriched_at=now_iso(), enrich_seconds=round(prepared.details_s, 2))
            self._time(item_id, "failed", prepared, 0.0)
            return "failed"

        self._save_details(item, prepared)
        note: str | None = None
        outcome = "transcribed"
        started = time.monotonic()
        with self.db.connect() as conn:
            has_transcript = get_transcript(conn, item_id) is not None
        if has_transcript:
            pass  # done in an earlier run
        elif prepared.media_path is not None:
            outcome, note = self._transcribe(item_id, prepared.media_path)
        else:
            error = prepared.media_error
            if isinstance(error, TooLong):
                note = str(error)
            else:
                reason = plain_reason(error or "No sound file")
                if reason.is_network or forbidden(error):
                    # Offline, or TikTok refused the file this time: not done.
                    # The save stays waiting, so the next run tries again.
                    with self.db.connect() as conn:
                        update_item(conn, item_id, error=f"Got the details, but not the sound. {reason.text}")
                    return "later" if reason.is_network else "refused"
                note = f"Got the details, but not the sound. {reason.text}"
            outcome = "details_only"
        transcribe_s = time.monotonic() - started

        seconds = prepared.details_s + prepared.sound_s + transcribe_s
        with self.db.connect() as conn:
            update_item(conn, item_id, status="enriched", error=note, enriched_at=now_iso(),
                        enrich_seconds=round(seconds, 2))
        self._time(item_id, outcome, prepared, transcribe_s)
        return outcome

    def _save_details(self, item: dict[str, Any], prepared: Prepared) -> None:
        details = prepared.details
        assert details is not None
        fields: dict[str, Any] = {
            "title": details.title,
            "description": details.description,
            "duration_s": details.duration_s,
            "posted_at": details.posted_at,
            "thumbnail_url": details.thumbnail_url or item.get("thumbnail_url"),
            # The export's author (if any) wins: it's what the user saw.
            "author": item.get("author") or details.author,
        }
        if prepared.thumbnail_name:
            fields["thumbnail_path"] = prepared.thumbnail_name
        with self.db.connect() as conn:
            update_item(conn, int(item["id"]), **fields)

    def _transcribe(self, item_id: int, media: Path) -> tuple[str, str | None]:
        if self.transcriber is None:
            folder = model_folder(self.paths.models, self.model_id)
            self.transcriber = self.transcriber_factory(folder, self.model_id, self.device)
        capture_frames(media, self.paths.thumbnails, item_id)  # pictures for the AI to look at
        try:
            result = self.transcriber.transcribe(media, check=self.ctx.check)
        except JobCancelled:
            raise  # keep the sound file; Resume carries on from here
        except NoSound:
            self._save_transcript(item_id, "", None)
            media.unlink(missing_ok=True)
            return "no_speech", "This video has no sound."
        except Exception as error:  # noqa: BLE001 - details are still kept
            return "details_only", f"Got the details, but couldn't turn the speech into text ({error})."
        self._save_transcript(item_id, result.text, result.language)
        media.unlink(missing_ok=True)  # the transcript is all we need
        if result.no_speech:
            return "no_speech", None
        return "transcribed", None

    def _save_transcript(self, item_id: int, text: str, language: str | None) -> None:
        assert self.transcriber is not None
        with self.db.connect() as conn:
            save_transcript(conn, item_id, text, language, self.transcriber.source)

    def _time(self, item_id: int, outcome: str, prepared: Prepared, transcribe_s: float) -> None:
        if len(self.timings) >= TIMINGS_KEPT:
            return
        self.timings.append({
            "id": item_id,
            "outcome": outcome,
            "details_s": round(prepared.details_s, 2),
            "sound_s": round(prepared.sound_s, 2),
            "transcribe_s": round(transcribe_s, 2),
            "total_s": round(prepared.details_s + prepared.sound_s + transcribe_s, 2),
        })

    # ---------- the end ----------

    def _summary(self, total: int) -> dict[str, Any]:
        counts = self.counts
        parts = []
        if counts["transcribed"]:
            parts.append(f"{counts['transcribed']:,} transcribed")
        if counts["no_speech"]:
            parts.append(f"{counts['no_speech']:,} with no speech")
        if counts["details_only"]:
            parts.append(f"{counts['details_only']:,} with details only")
        if counts["failed"]:
            parts.append(f"{counts['failed']:,} couldn't be read")
        if counts["later"] + counts["refused"]:
            parts.append(f"{counts['later'] + counts['refused']:,} to try again later")
        worked = sum(counts.values())
        if worked == 0:
            message = f"All {plural(total, 'video')} were already done."
        else:
            message = f"Finished {plural(worked, 'video')}: " + ", ".join(parts) + "."
        device = self.transcriber.device_used if self.transcriber else None
        return {
            "message": message,
            **counts,
            "model": self.model_id,
            "device": device,
            "timings": self.timings,
        }
