"""Tests for the "enrich" job and the transcripts routes, with a fake
yt-dlp (FakeFetcher) and a fake speech model (FakeTranscriber)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.items_repo import NewItem, get_item_row, get_transcript, upsert_item
from app.enrich.fetch import TooLong, VideoDetails
from app.enrich.job import OFFLINE, make_enrich_handler
from app.enrich.speech_models import COMPLETE_MARKER, model_folder
from app.enrich.transcribe import Transcript
from app.services import AppServices
from tests.test_jobs import wait_for_status

NETWORK = "ERROR: [TikTok] 1: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>"


class FakeFetcher:
    """What each video does is decided by a word in its link."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def details(self, url: str, platform: str) -> tuple[VideoDetails, Any]:
        self.calls.append(url)
        if "private" in url:
            raise RuntimeError("ERROR: [TikTok] 1: This video is private")
        if "offline" in url:
            raise RuntimeError(NETWORK)
        return VideoDetails(title=None, description=f"Caption of {url}", author="chef",
                            duration_s=30.0, thumbnail_url="https://cdn/t.jpg",
                            posted_at="2024-01-01T00:00:00Z"), url

    def download_media(self, handle: Any, folder: Path, stem: str) -> Path:
        url = str(handle)
        if "refused" in url:
            raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        if "nosound" in url:
            raise RuntimeError("ERROR: [TikTok] 1: Requested format is not available")
        if "long" in url:
            raise TooLong("This video is longer than 90 minutes, so it isn't transcribed.")
        path = folder / f"{stem}.mp4"
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text("music" if "music" in url else "speech: boil the pasta", encoding="utf-8")
        return path

    def download_thumbnail(self, url: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpeg")
        return path


class FakeTranscriber:
    source = "whisper-fake"
    device_used = "cpu"
    gate: threading.Event | None = None  # set by a test to hold transcription

    def __init__(self, folder: Path, model_id: str, device: str) -> None:
        self.model_id = model_id

    def transcribe(self, path: Path, check: Any = None) -> Transcript:
        if FakeTranscriber.gate is not None:
            while not FakeTranscriber.gate.wait(0.02):
                if check:
                    check()
        content = path.read_text(encoding="utf-8")
        if content == "music":
            return Transcript("", None, no_speech=True)
        return Transcript(content.removeprefix("speech: "), "en", no_speech=False)

    def close(self) -> None:
        pass


@pytest.fixture
def fetcher(svc: AppServices) -> FakeFetcher:
    fake = FakeFetcher()
    downloads: list[str] = []

    def fake_model_download(models_root: Path, model_id: str, report: Any = None, check: Any = None) -> Path:
        downloads.append(model_id)
        if report:
            report(50, 100)
        folder = model_folder(models_root, model_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / COMPLETE_MARKER).write_text("ok")
        return folder

    fake.model_downloads = downloads  # type: ignore[attr-defined]
    svc.runner.register(
        "enrich",
        make_enrich_handler(svc.db, svc.paths, svc.settings, fetcher_factory=lambda: fake,
                            transcriber_factory=FakeTranscriber, model_downloader=fake_model_download),
    )
    FakeTranscriber.gate = None
    return fake


def add_items(svc: AppServices, *words: str) -> list[int]:
    ids = []
    with svc.db.connect() as conn:
        for number, word in enumerate(words):
            item_id, _ = upsert_item(conn, NewItem(
                platform="tiktok",
                url=f"https://www.tiktokv.com/share/video/{word}-{number}/",
                saved_at=f"2024-01-{number + 1:02d}T00:00:00Z",
            ))
            ids.append(item_id)
    return ids


def run(svc: AppServices, ids: list[int], *statuses: str) -> dict[str, Any]:
    svc.runner.start()
    job_id = svc.runner.submit("enrich", "Transcripts", {"item_ids": ids})
    return wait_for_status(svc, job_id, *(statuses or ("done", "failed")))


def item(svc: AppServices, item_id: int) -> dict[str, Any]:
    with svc.db.connect() as conn:
        row = get_item_row(conn, item_id)
        assert row is not None
        row["transcript"] = get_transcript(conn, item_id)
    return row


def test_each_kind_of_video_ends_up_right(svc: AppServices, fetcher: FakeFetcher) -> None:
    ok, music, private, nosound, long = add_items(svc, "ok", "music", "private", "nosound", "long")
    job = run(svc, [ok, music, private, nosound, long])
    assert job["status"] == "done", job
    assert job["message"] == (
        "Finished 5 videos: 1 transcribed, 1 with no speech, 2 with details only, 1 couldn't be read."
    )
    assert fetcher.model_downloads == ["small"]  # type: ignore[attr-defined]

    first = item(svc, ok)
    assert first["status"] == "enriched" and first["error"] is None
    assert first["transcript"] == {"text": "boil the pasta", "language": "en", "source": "whisper-fake"}
    assert first["description"].startswith("Caption of") and first["author"] == "chef"
    assert first["duration_s"] == 30.0 and first["posted_at"] == "2024-01-01T00:00:00Z"
    assert first["thumbnail_path"] == f"{ok}.jpg" and (svc.paths.thumbnails / f"{ok}.jpg").exists()
    assert first["enrich_seconds"] is not None and first["enriched_at"]
    assert list(svc.paths.audio.iterdir()) == []  # sound files are deleted once transcribed

    assert item(svc, music)["transcript"]["text"] == ""
    blocked = item(svc, private)
    assert blocked["status"] == "failed"
    assert blocked["error"] == "This video is private, so only the person who posted it can see it."
    no_sound = item(svc, nosound)
    assert no_sound["status"] == "enriched" and no_sound["transcript"] is None
    assert no_sound["error"].startswith("Got the details, but not the sound.")
    assert "longer than 90 minutes" in item(svc, long)["error"]

    timings = job["result"]["timings"]
    assert [t["outcome"] for t in timings] == ["transcribed", "no_speech", "failed", "details_only", "details_only"]
    assert set(timings[0]) == {"id", "outcome", "details_s", "sound_s", "transcribe_s", "total_s"}


def test_running_again_skips_finished_videos(svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "ok", "ok")
    run(svc, ids)
    calls = len(fetcher.calls)
    again = run(svc, ids)
    assert again["message"] == "All 2 videos were already done."
    assert len(fetcher.calls) == calls
    assert len(fetcher.model_downloads) == 1  # type: ignore[attr-defined]


def test_losing_the_internet_stops_the_job_and_keeps_items_waiting(
    svc: AppServices, fetcher: FakeFetcher
) -> None:
    ids = add_items(svc, "ok", "offline", "offline", "offline", "ok")
    job = run(svc, ids)
    assert job["status"] == "failed"
    assert job["error"] == OFFLINE
    assert item(svc, ids[0])["status"] == "enriched"
    for item_id in ids[1:4]:
        waiting = item(svc, item_id)
        assert waiting["status"] == "imported"  # not failed: it will work later
        assert waiting["error"].startswith("Couldn't reach the website")
    assert item(svc, ids[4])["status"] == "imported"


def test_tiktok_refusing_the_file_keeps_the_save_waiting(svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "refused", "refused", "refused", "refused", "ok")
    job = run(svc, ids)
    assert job["status"] == "done"  # TikTok saying no isn't being offline
    assert "4 to try again later" in job["message"]
    for item_id in ids[:4]:
        waiting = item(svc, item_id)
        assert waiting["status"] == "imported" and waiting["description"]  # details kept
        assert "HTTP Error 403" in waiting["error"]
    assert item(svc, ids[4])["status"] == "enriched"


def test_one_network_hiccup_does_not_stop_the_batch(svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "offline", "ok")
    job = run(svc, ids)
    assert job["status"] == "done"
    assert "1 to try again later" in job["message"]


def test_cancel_keeps_the_sound_file_for_next_time(svc: AppServices, fetcher: FakeFetcher) -> None:
    FakeTranscriber.gate = threading.Event()
    (item_id,) = add_items(svc, "ok")
    svc.runner.start()
    job_id = svc.runner.submit("enrich", "Transcripts", {"item_ids": [item_id]})
    wait_for_status(svc, job_id, "running")
    for _ in range(250):
        message = (svc.jobs.get(job_id) or {}).get("message") or ""
        if message.startswith("Transcribing"):
            break
        threading.Event().wait(0.02)
    else:
        raise AssertionError("never got to transcribing")
    svc.runner.cancel(job_id)
    wait_for_status(svc, job_id, "cancelled")
    assert item(svc, item_id)["status"] == "imported"
    assert (svc.paths.audio / f"{item_id}.mp4").exists()

    # Resume: the sound file is reused, not downloaded again.
    FakeTranscriber.gate.set()
    svc.runner.resume(job_id)
    done = wait_for_status(svc, job_id, "done")
    assert done["result"]["transcribed"] == 1
    assert item(svc, item_id)["transcript"]["text"] == "boil the pasta"


# ---------- routes ----------


def test_overview_counts_and_speech_settings(api: TestClient, svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "ok", "music", "private", "ok")
    run(svc, ids[:3])
    data = api.get("/api/enrich").json()
    assert data["counts"] == {
        "total": 4, "waiting": 1, "done": 2, "failed": 1, "no_speech": 1, "gone": 0,
        "failed_reasons": [{"text": "This video is private, so only the person who posted it can see it.", "count": 1}],
    }
    speech = data["speech"]
    assert speech["model"] == "small" and speech["device"] == "auto"
    assert [m["id"] for m in speech["models"]] == ["tiny", "base", "small", "medium", "large-v3-turbo"]
    assert next(m for m in speech["models"] if m["id"] == "small")["downloaded"] is True


def test_changing_speech_settings(api: TestClient, svc: AppServices) -> None:
    changed = api.put("/api/enrich/settings", json={"model": "base", "device": "cpu"}).json()
    assert (changed["model"], changed["device"]) == ("base", "cpu")
    assert svc.settings.get("transcription.model") == "base"
    assert api.put("/api/enrich/settings", json={"model": "huge"}).status_code == 400
    assert api.put("/api/enrich/settings", json={"device": "tpu"}).status_code == 400


def test_start_picks_the_newest_waiting_saves(api: TestClient, svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "ok", "ok", "ok", "ok")  # saved on Jan 1, 2, 3, 4
    job = api.post("/api/enrich/start", json={"count": 2}).json()
    assert job["params"]["item_ids"] == [ids[3], ids[2]]
    assert job["title"] == "Transcripts for 2 videos"
    wait_for_status(svc, job["id"], "done")

    everything = api.post("/api/enrich/start", json={"count": None}).json()
    assert everything["params"]["item_ids"] == [ids[1], ids[0]]
    wait_for_status(svc, everything["id"], "done")

    response = api.post("/api/enrich/start", json={"count": 5})
    assert response.status_code == 400
    assert "already has its transcript" in response.json()["detail"]
    assert api.post("/api/enrich/start", json={"which": "failed"}).status_code == 400
    assert api.post("/api/enrich/start", json={"which": "other"}).status_code == 400
    assert api.post("/api/enrich/start", json={"count": 0}).status_code == 422


def test_failed_videos_can_be_tried_again(api: TestClient, svc: AppServices, fetcher: FakeFetcher) -> None:
    ids = add_items(svc, "private")
    run(svc, ids)
    job = api.post("/api/enrich/start", json={"count": None, "which": "failed"}).json()
    assert job["params"]["item_ids"] == ids
    assert job["title"] == "Try 1 failed video again"


def test_recent_videos_and_thumbnails(api: TestClient, svc: AppServices, fetcher: FakeFetcher) -> None:
    ok, music, private = add_items(svc, "ok", "music", "private")
    run(svc, [ok, music, private])
    recent = {row["id"]: row for row in api.get("/api/enrich/recent").json()}
    assert set(recent) == {ok, music, private}
    assert recent[ok]["transcript_preview"] == "boil the pasta"
    assert recent[ok]["title"].startswith("Caption of") and recent[ok]["platform_name"] == "TikTok"
    assert recent[ok]["has_thumbnail"] is True and recent[ok]["no_speech"] is False
    assert recent[music]["no_speech"] is True
    assert recent[private]["status"] == "failed" and recent[private]["transcript_chars"] is None

    picture = api.get(f"/api/items/{ok}/thumbnail")
    assert picture.status_code == 200 and picture.content == b"jpeg"
    assert api.get(f"/api/items/{private}/thumbnail").status_code == 404
    assert api.get("/api/items/9999/thumbnail").status_code == 404


def test_thumbnail_route_stays_inside_its_folder(api: TestClient, svc: AppServices) -> None:
    (item_id,) = add_items(svc, "ok")
    (svc.paths.root / "secret.txt").write_text("no")
    with svc.db.connect() as conn:
        conn.execute("UPDATE items SET thumbnail_path = '../secret.txt' WHERE id = ?", (item_id,))
    assert api.get(f"/api/items/{item_id}/thumbnail").status_code == 404
