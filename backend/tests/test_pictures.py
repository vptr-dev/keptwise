"""The AI looking at pictures from a video: stills, the cover, each
provider's own way of sending them, and models that can't see."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from app.ai.http import HttpError
from app.ai.pictures import capture_frames, frame_paths, pictures_for
from app.ai.registry import make_provider
from app.ai.sorting import tags
from app.ai.sorting.settings import SortingSettings, save
from app.services import AppServices
from tests.fakes import FakeNet
from tests.test_sorting_job import OLLAMA, fake_ai, ollama, run_job, seed  # noqa: F401 - ollama is a fixture

SEE = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "What is this?", "images": ["QUJD"]}]


def tiny_video(path: Path, seconds: int = 3) -> Path:
    """A few seconds of plain colour that changes, small enough for a test."""
    import av
    import numpy as np

    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for n in range(seconds * 10):
            picture = np.full((48, 64, 3), (n * 8) % 255, dtype=np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(picture, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def cover(folder: Path, name: str = "1.jpg") -> str:
    from PIL import Image

    Image.new("RGB", (1200, 800), (200, 30, 30)).save(folder / name, "JPEG")
    return name


def test_stills_are_kept_from_a_video_and_shrunk_for_the_ai(tmp_path: Path) -> None:
    from PIL import Image

    video = tiny_video(tmp_path / "7.mp4")
    assert capture_frames(video, tmp_path, 7) == 3
    assert [p.name for p in frame_paths(tmp_path, 7)] == ["7-f1.jpg", "7-f2.jpg", "7-f3.jpg"]
    sent = pictures_for(tmp_path, 7, None)
    assert len(sent) == 3 and base64.b64decode(sent[0])[:2] == b"\xff\xd8"  # JPEG

    # No stills: the cover picture is used, shrunk to 512 pixels at most.
    only = pictures_for(tmp_path, 1, cover(tmp_path))
    assert len(only) == 1
    import io
    assert max(Image.open(io.BytesIO(base64.b64decode(only[0]))).size) == 512
    assert pictures_for(tmp_path, 2, None) == [] and pictures_for(tmp_path, 2, "../outside.jpg") == []
    # A file that isn't a video is no reason to fail.
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    assert capture_frames(tmp_path / "broken.mp4", tmp_path, 9) == 0


def test_each_provider_sends_pictures_its_own_way() -> None:
    net = FakeNet().on("POST", f"{OLLAMA}/api/chat", {"message": {"content": "a cat"}})
    make_provider("ollama", net.client(), model="gemma4:12b").chat(SEE)
    assert net.requests[0]["json"]["messages"][1]["images"] == ["QUJD"]

    net = FakeNet().on("POST", "https://api.openai.com/v1/chat/completions", {"choices": [{"message": {"content": "a cat"}}]})
    make_provider("openai", net.client(), model="gpt-x", api_key="k").chat(SEE)
    parts = net.requests[0]["json"]["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "What is this?"}
    assert parts[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
    assert net.requests[0]["json"]["messages"][0] == {"role": "system", "content": "Be brief."}

    net = FakeNet().on("POST", "https://api.anthropic.com/v1/messages", {"content": [{"type": "text", "text": "a cat"}]})
    make_provider("anthropic", net.client(), model="claude-haiku-5-5", api_key="k").chat(SEE)
    blocks = net.requests[0]["json"]["messages"][0]["content"]
    assert blocks[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}}
    assert blocks[1] == {"type": "text", "text": "What is this?"}


def test_notes_are_written_with_the_videos_pictures(svc: AppServices, ollama: FakeNet) -> None:  # noqa: F811
    (pasta,) = seed(svc, "pasta")
    name = cover(svc.paths.thumbnails, f"{pasta}.jpg")
    with svc.db.connect() as conn:
        conn.execute("UPDATE items SET thumbnail_path = ? WHERE id = ?", (name, pasta))
    assert run_job(svc, "notes", [pasta])["status"] == "done"
    sent = next(r["json"] for r in ollama.requests if r["url"].endswith("/api/chat"))
    question = next(m for m in sent["messages"] if "Caption:" in m["content"])
    assert len(question["images"]) == 1 and "1 picture from the video is attached" in question["content"]


def test_a_model_that_cant_see_is_asked_again_without_pictures(svc: AppServices, net: FakeNet) -> None:
    seen: list[bool] = []

    def reply(payload: dict[str, Any] | None) -> dict[str, Any]:
        assert payload is not None
        with_pictures = any(m.get("images") for m in payload["messages"])
        seen.append(with_pictures)
        if with_pictures:
            raise HttpError("HTTP 400", status=400, body='{"error":"this model does not support images"}')
        return fake_ai(payload)

    net.on("GET", f"{OLLAMA}/api/tags", {"models": [{"name": "gemma4:12b"}]})
    net.on("POST", f"{OLLAMA}/api/chat", reply)
    pasta, london = seed(svc, "pasta", "london")
    for item_id in (pasta, london):
        name = cover(svc.paths.thumbnails, f"{item_id}.jpg")
        with svc.db.connect() as conn:
            conn.execute("UPDATE items SET thumbnail_path = ? WHERE id = ?", (name, item_id))
    job = run_job(svc, "notes", [pasta, london])
    assert job["status"] == "done" and job["message"].startswith("Wrote notes for 2 videos")
    # Tried with the picture once; after that the rest of the job goes without.
    assert seen == [True, False, False]


def test_pictures_and_tagging_can_be_switched_off(svc: AppServices, ollama: FakeNet) -> None:  # noqa: F811
    save(svc.settings, SortingSettings(look_at_pictures=False, auto_tag=False))
    (pasta,) = seed(svc, "pasta")
    name = cover(svc.paths.thumbnails, f"{pasta}.jpg")
    with svc.db.connect() as conn:
        conn.execute("UPDATE items SET thumbnail_path = ? WHERE id = ?", (name, pasta))
    assert run_job(svc, "notes", [pasta])["status"] == "done"
    sent = next(r["json"] for r in ollama.requests if r["url"].endswith("/api/chat"))
    assert not any(m.get("images") for m in sent["messages"])
    assert "- tags: an empty list." in json.dumps(sent)
    with svc.db.connect() as conn:
        assert [t for t in tags.of_item(conn, pasta) if t["source"] == "ai"] == []  # tagging by hand
