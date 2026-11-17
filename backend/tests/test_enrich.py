"""Tests for the enrichment building blocks (no network, no real model)."""

from __future__ import annotations

import io
import json
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.enrich.download import DownloadError, download_file
from app.enrich.errors import plain_reason
from app.enrich.fetch import details_from_info, save_thumbnail
from app.enrich.speech_models import download_model, is_downloaded, model_folder
from app.enrich.transcribe import SAMPLE_RATE, NoSound, Transcriber, decode_audio, keep_segments
from app.jobs.runner import JobCancelled

# ---------- plain reasons ----------


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("ERROR: [TikTok] 7300000000000000001: This video is private", "private"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "private"),
        ("ERROR: [TikTok] 7000000000000000001: Your IP address is blocked from accessing this post", "gone"),
        ("ERROR: [TikTok] 1: Video not available, status code 10204", "gone"),
        ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", "gone"),
        ("ERROR: [Instagram] C1: Requested content is not available, rate-limit reached or login required", "login"),
        ("ERROR: [youtube] abc: Sign in to confirm your age", "login"),
        ("ERROR: [youtube] abc: The uploader has not made this video available in your country", "region"),
        ("ERROR: Unsupported URL: https://example.com/page", "no_media"),
        ("ERROR: [TikTok] 1: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network"),
        ("ERROR: [TikTok] 1: Read timed out.", "network"),
    ],
)
def test_reasons_are_plain_english(message: str, kind: str) -> None:
    reason = plain_reason(message)
    assert reason.kind == kind
    assert "ERROR" not in reason.text and "[" not in reason.text


def test_unknown_errors_keep_a_short_message() -> None:
    reason = plain_reason("ERROR: [TikTok] 123: Something odd happened")
    assert reason.kind == "other"
    assert reason.text == "Couldn't read this video: Something odd happened"
    assert plain_reason(RuntimeError("x" * 500)).text.endswith("…")


# ---------- details ----------


def test_tiktok_details_skip_the_fake_title() -> None:
    info = {
        "title": "Quick pasta for busy days. #fyp #pasta",
        "description": "Quick pasta for busy days. #fyp #pasta #dinner",
        "uploader": "pasta.chef",
        "duration": 195,
        "thumbnail": "https://cdn.example/t.jpeg",
        "timestamp": 1700000000,
    }
    details = details_from_info(info)
    assert details.title is None  # TikTok has no titles
    assert details.description == info["description"]
    assert details.author == "pasta.chef"
    assert details.duration_s == 195.0
    assert details.posted_at == "2023-11-14T22:13:20Z"


def test_youtube_details_keep_the_title() -> None:
    details = details_from_info(
        {"title": "Easy pasta", "description": "Recipe below", "channel": "Chef", "upload_date": "20240105"}
    )
    assert details.title == "Easy pasta"
    assert details.author == "Chef"
    assert details.posted_at == "2024-01-05T00:00:00Z"
    assert details.duration_s is None


def test_thumbnails_are_saved_small(tmp_path: Path) -> None:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1080, 1920), "orange").save(buffer, "PNG")
    path = save_thumbnail(buffer.getvalue(), tmp_path / "1.jpg")
    with Image.open(path) as image:
        assert image.format == "JPEG"
        assert image.size == (480, 853)
    # Something Pillow can't read is kept as it is.
    odd = save_thumbnail(b"not an image", tmp_path / "2.jpg")
    assert odd.read_bytes() == b"not an image"


# ---------- sound ----------


def write_wav(path: Path, seconds: float = 1.0, rate: int = 44_100, channels: int = 2) -> Path:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        samples = (int(8000 * math.sin(2 * math.pi * 440 * n / rate)) for n in range(frames))
        file.writeframes(b"".join(struct.pack("<" + "h" * channels, *([s] * channels)) for s in samples))
    return path


def test_decode_audio_gives_16khz_mono(tmp_path: Path) -> None:
    audio = decode_audio(write_wav(tmp_path / "tone.wav", seconds=1.5))
    assert audio.dtype.name == "float32"
    assert abs(len(audio) - 1.5 * SAMPLE_RATE) < 200
    assert 0.1 < float(abs(audio).max()) <= 1.0


@dataclass
class Segment:
    text: str
    no_speech_prob: float = 0.1
    avg_logprob: float = -0.3
    compression_ratio: float = 1.5


def test_made_up_lines_are_left_out() -> None:
    text = keep_segments([
        Segment(" Hello there."),
        Segment(" Thanks for watching!", no_speech_prob=0.9, avg_logprob=-1.5),
        Segment(" la la la la la la", compression_ratio=3.1),
        Segment(" Bye."),
    ])
    assert text == "Hello there. Bye."


def test_cancel_works_between_lines() -> None:
    def check() -> None:
        raise JobCancelled

    with pytest.raises(JobCancelled):
        keep_segments([Segment("a")], check)


@dataclass
class Info:
    language: str = "en"
    language_probability: float = 0.98


class FakeModel:
    def __init__(self, device: str, segments: list[Segment], info: Info, fail_on_use: bool = False) -> None:
        self.device = device
        self.segments = segments
        self.info = info
        self.fail_on_use = fail_on_use
        self.batched = False
        self.options: dict[str, Any] = {}

    def transcribe(self, audio: Any, **options: Any) -> tuple[Any, Info]:
        self.options = options
        if self.fail_on_use:
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        return iter(self.segments), self.info


@pytest.fixture(autouse=True)
def fresh_gpu_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts as if the app had just opened."""
    from app.enrich import transcribe

    monkeypatch.setattr(transcribe, "_gpu_failed", False)


def make_transcriber(tmp_path: Path, segments: list[Segment], info: Info, cuda: int = 0,
                     gpu_works: bool = True) -> tuple[Transcriber, list[str]]:
    made: list[str] = []

    def factory(folder: str, device: str, compute_type: str, threads: int) -> FakeModel:
        made.append(f"{device}/{compute_type}")
        return FakeModel(device, segments, info, fail_on_use=device == "cuda" and not gpu_works)

    def batcher(model: FakeModel) -> FakeModel:
        model.batched = True
        return model

    return Transcriber(tmp_path, "small", "auto", factory=factory, cuda_devices=lambda: cuda, batcher=batcher), made


def test_transcriber_returns_the_words(tmp_path: Path) -> None:
    transcriber, made = make_transcriber(tmp_path, [Segment(" Boil the pasta.")], Info())
    result = transcriber.transcribe(write_wav(tmp_path / "a.wav"))
    assert (result.text, result.language, result.no_speech) == ("Boil the pasta.", "en", False)
    assert made == ["cpu/int8"] and transcriber.device_used == "cpu"
    assert not transcriber._model.batched and "batch_size" not in transcriber._model.options
    assert transcriber.source == "whisper-small"


def test_music_only_counts_as_no_speech(tmp_path: Path) -> None:
    transcriber, _ = make_transcriber(tmp_path, [Segment(" ༼ ༽ ༽ ༽")], Info("jw", 0.26))
    result = transcriber.transcribe(write_wav(tmp_path / "a.wav"))
    assert result.no_speech and result.text == "" and result.language is None


def test_graphics_card_is_used_when_it_works(tmp_path: Path) -> None:
    transcriber, made = make_transcriber(tmp_path, [Segment(" Hi there.")], Info(), cuda=1)
    transcriber.transcribe(write_wav(tmp_path / "a.wav"))
    assert made == ["cuda/float16"] and transcriber.device_used == "gpu"
    # The card gets 8 pieces at once; that made it 4x faster on the user's PC.
    assert transcriber._model.batched and transcriber._model.options["batch_size"] == 8


def test_missing_nvidia_files_fall_back_to_the_processor(tmp_path: Path) -> None:
    transcriber, made = make_transcriber(tmp_path, [Segment(" Hi there.")], Info(), cuda=1, gpu_works=False)
    result = transcriber.transcribe(write_wav(tmp_path / "a.wav"))
    assert result.text == "Hi there."
    assert made == ["cuda/float16", "cpu/int8"] and transcriber.device_used == "cpu"


def test_a_failed_graphics_card_is_not_tried_again(tmp_path: Path) -> None:
    # Retrying the card after it failed hung the installed app, so it's tried once per run.
    first, made_first = make_transcriber(tmp_path, [Segment(" Hi.")], Info(), cuda=1, gpu_works=False)
    first.transcribe(write_wav(tmp_path / "a.wav"))
    second, made_second = make_transcriber(tmp_path, [Segment(" Hi.")], Info(), cuda=1, gpu_works=False)
    second.transcribe(write_wav(tmp_path / "b.wav"))
    assert made_first == ["cuda/float16", "cpu/int8"]
    assert made_second == ["cpu/int8"] and second.device_used == "cpu"


def test_no_cublas_means_no_graphics_card(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.enrich import transcribe

    monkeypatch.setattr(transcribe, "cublas_loadable", lambda: False)
    assert transcribe._cuda_devices() == 0


def test_nvidia_folders_are_found_when_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.machinery
    import importlib.util

    from app.enrich import transcribe

    (tmp_path / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    (tmp_path / "nvidia" / "cudnn" / "lib").mkdir(parents=True)  # no bin folder: skipped
    spec = importlib.machinery.ModuleSpec("nvidia", None, is_package=True)
    spec.submodule_search_locations = [str(tmp_path / "nvidia")]
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec if name == "nvidia" else None)
    assert transcribe.nvidia_dll_folders() == [tmp_path / "nvidia" / "cublas" / "bin"]
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert transcribe.nvidia_dll_folders() == []


def test_no_sound_track(tmp_path: Path) -> None:
    import av

    path = tmp_path / "silent.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=1)
        stream.width, stream.height = 16, 16
        import numpy as np

        frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    with pytest.raises(NoSound):
        decode_audio(path)


# ---------- downloads ----------


class FakeResponse:
    def __init__(self, status: int, body: bytes, fail_after: int | None = None) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self._body = io.BytesIO(body)
        self._fail_after = fail_after
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self._fail_after is not None and self._body.tell() >= self._fail_after:
            raise ConnectionResetError("connection reset")
        if self._fail_after is not None:
            size = min(size if size > 0 else 1 << 30, self._fail_after - self._body.tell())
        return self._body.read(size)

    def close(self) -> None:
        self.closed = True


class FakeServer:
    """Serves files; honours Range like a real server (or not)."""

    def __init__(self, files: dict[str, bytes], honour_range: bool = True) -> None:
        self.files = files
        self.honour_range = honour_range
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.cut_after: dict[str, int] = {}

    def __call__(self, url: str, headers: dict[str, str]) -> FakeResponse:
        self.requests.append((url, headers))
        body = self.files[url]
        if "Range" in headers and self.honour_range:
            start = int(headers["Range"].removeprefix("bytes=").rstrip("-"))
            if start >= len(body):
                return FakeResponse(416, b"")
            return FakeResponse(206, body[start:], self.cut_after.pop(url, None))
        return FakeResponse(200, body, self.cut_after.pop(url, None))


def test_download_resumes_after_a_cut(tmp_path: Path) -> None:
    server = FakeServer({"https://x/model.bin": b"0123456789" * 100})
    server.cut_after["https://x/model.bin"] = 300
    dest = tmp_path / "model.bin"
    with pytest.raises(DownloadError, match="carry on"):
        download_file("https://x/model.bin", dest, expected_size=1000, opener=server)
    assert (tmp_path / "model.bin.part").stat().st_size == 300

    seen: list[int] = []
    download_file("https://x/model.bin", dest, expected_size=1000, on_bytes=seen.append, opener=server)
    assert dest.read_bytes() == b"0123456789" * 100
    assert server.requests[-1][1] == {"Range": "bytes=300-"}
    assert sum(seen) == 1000  # the 300 we had + the 700 that arrived


def test_download_starts_again_if_the_server_ignores_range(tmp_path: Path) -> None:
    server = FakeServer({"https://x/f": b"abcdef"}, honour_range=False)
    (tmp_path / "f.part").write_bytes(b"zz")
    download_file("https://x/f", tmp_path / "f", expected_size=6, opener=server)
    assert (tmp_path / "f").read_bytes() == b"abcdef"


def test_cancel_keeps_the_part_file(tmp_path: Path) -> None:
    server = FakeServer({"https://x/f": b"a" * 10})

    def check() -> None:
        raise JobCancelled

    with pytest.raises(JobCancelled):
        download_file("https://x/f", tmp_path / "f", expected_size=10, check=check, opener=server)
    assert (tmp_path / "f.part").exists() and not (tmp_path / "f").exists()


def tree_for(files: dict[str, bytes]) -> bytes:
    entries = [{"type": "file", "path": name, "size": len(body)} for name, body in files.items()]
    entries.append({"type": "file", "path": "README.md", "size": 5})  # not needed
    return json.dumps(entries).encode()


def test_speech_model_download(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"m" * 2048, "tokenizer.json": b"{}", "vocabulary.txt": b"a\nb"}
    hub = "https://huggingface.co"
    repo = "Systran/faster-whisper-tiny"
    server = FakeServer({
        f"{hub}/api/models/{repo}/tree/main": tree_for(files),
        **{f"{hub}/{repo}/resolve/main/{name}": body for name, body in files.items()},
    })
    progress: list[tuple[int, int]] = []
    assert not is_downloaded(tmp_path, "tiny")
    folder = download_model(tmp_path, "tiny", report=lambda d, t: progress.append((d, t)), opener=server)
    assert folder == model_folder(tmp_path, "tiny")
    assert sorted(p.name for p in folder.iterdir()) == [".complete", *sorted(files)]
    assert is_downloaded(tmp_path, "tiny")
    assert progress[-1] == (sum(map(len, files.values())), sum(map(len, files.values())))
    assert not any("README" in url for url, _ in server.requests)
    # Second time: nothing is downloaded.
    count = len(server.requests)
    download_model(tmp_path, "tiny", opener=server)
    assert len(server.requests) == count


def test_speech_model_needs_disk_space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    from collections import namedtuple

    files = {"model.bin": b"m" * 10}
    repo = "Systran/faster-whisper-tiny"
    server = FakeServer({f"https://huggingface.co/api/models/{repo}/tree/main": tree_for(files)})
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(1, 1, 1000))
    with pytest.raises(DownloadError, match="Not enough free disk space"):
        download_model(tmp_path, "tiny", opener=server)


def test_bundled_ffmpeg_is_only_used_by_the_installed_app(tmp_path: Path) -> None:
    from app.enrich.fetch import bundled_ffmpeg

    assert bundled_ffmpeg(tmp_path, frozen=True) is None  # not shipped
    (tmp_path / "ffmpeg").mkdir()
    (tmp_path / "ffmpeg" / "ffmpeg.exe").write_bytes(b"")
    assert bundled_ffmpeg(tmp_path, frozen=True) == str(tmp_path / "ffmpeg" / "ffmpeg.exe")
    assert bundled_ffmpeg(tmp_path, frozen=False) is None  # running from source


def test_tiktok_403_reads_the_page_again_for_fresh_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.enrich import fetch
    from app.enrich.fetch import DOWNLOAD_TRIES, YtDlpFetcher, _Page

    monkeypatch.setattr(fetch, "RETRY_PAUSE_S", 0)

    class Fetcher(YtDlpFetcher):
        def __init__(self, fails: int) -> None:
            super().__init__(ffmpeg_location="ffmpeg")
            self.fails, self.reads = fails, 0

        def _read(self, url: str, options: dict) -> _Page:  # type: ignore[override]
            self.reads += 1
            return _Page(url, options, {"id": self.reads}, [])

        def _download(self, page: _Page, folder: Path, stem: str) -> Path:
            if self.fails:
                self.fails -= 1
                raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
            path = folder / f"{stem}.mp4"
            path.write_bytes(b"x")
            return path

    fetcher = Fetcher(fails=1)
    _, page = fetcher.details("https://www.tiktok.com/@a/video/1", "tiktok")
    assert fetcher.download_media(page, tmp_path, "1") == tmp_path / "1.mp4"
    assert fetcher.reads == 2  # one fresh read after the 403

    stubborn = Fetcher(fails=DOWNLOAD_TRIES)
    _, page = stubborn.details("https://www.tiktok.com/@a/video/2", "tiktok")
    with pytest.raises(RuntimeError, match="403"):
        stubborn.download_media(page, tmp_path, "2")
    assert stubborn.reads == DOWNLOAD_TRIES

    other = Fetcher(fails=0)
    other._download = lambda *a: (_ for _ in ()).throw(RuntimeError("HTTP Error 404"))  # type: ignore[method-assign]
    _, page = other.details("https://www.tiktok.com/@a/video/3", "tiktok")
    with pytest.raises(RuntimeError, match="404"):
        other.download_media(page, tmp_path, "3")
    assert other.reads == 1  # only 403 is retried
