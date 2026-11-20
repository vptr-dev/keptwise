"""Speech to text on this PC with faster-whisper.

Lessons from real saves (Nov 2026):
- faster-whisper 1.2.1 can't open files with PyAV 19 by itself, so we turn
  the sound into numbers ourselves (decode_audio) and hand those over.
- Videos with only music make Whisper invent lyrics or symbols, slowly.
  The second pass and low-confidence languages need stronger evidence
  from each sentence before their text is kept.
- Using the graphics card needs NVIDIA's cuBLAS files (ctranslate2 brings
  cuDNN itself). They come from the optional backend/requirements-gpu.txt,
  inside the venv, so Windows has to be told where they are
  (use_nvidia_files). If they're missing, the model quietly runs on the
  processor instead.
- On the graphics card, one piece at a time was no faster than the processor
  (about 20 s for a 3-minute talking video). Handing it 8 pieces at once
  (BatchedInferencePipeline) took 4.5 s. On the processor batching doesn't
  help, so it keeps the one-at-a-time way.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16_000
MIN_LANGUAGE_CONFIDENCE = 0.5
# Whisper's usual tests for a made-up line.
MAX_COMPRESSION_RATIO = 2.4
NO_SPEECH_PROB = 0.6
LOW_LOG_PROB = -1.0
SECOND_PASS_SECONDS = 180
GPU_BATCH_SIZE = 8  # pieces of a video the graphics card works on at once


class NoSound(Exception):
    """The file has no sound track at all."""


@dataclass
class Transcript:
    text: str
    language: str | None
    no_speech: bool


def decode_audio(path: Path) -> Any:
    """Read any audio/video file as 16 kHz mono float32 numbers (a numpy array)."""
    import av
    import numpy as np

    chunks = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise NoSound("This video has no sound.")
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):  # whatever is left in the resampler
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise NoSound("This video has no sound.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def keep_segments(
    segments: Iterable[Any], check: Callable[[], None] | None = None, *, strict: bool = False,
) -> str:
    """Join the lines Whisper heard, leaving out the ones it probably made up."""
    lines: list[str] = []
    for segment in segments:
        if check:
            check()
        if segment.no_speech_prob > NO_SPEECH_PROB and segment.avg_logprob < LOW_LOG_PROB:
            continue
        if strict and (segment.no_speech_prob > 0.45 or segment.avg_logprob < LOW_LOG_PROB):
            continue
        if segment.compression_ratio > MAX_COMPRESSION_RATIO:
            continue  # the same words over and over
        text = segment.text.strip()
        if text:
            lines.append(text)
    return " ".join(lines)


def _has_words(text: str) -> bool:
    return sum(ch.isalpha() for ch in text) >= 3


# (model folder, device, compute type, cpu threads) -> a WhisperModel
ModelFactory = Callable[[str, str, str, int], Any]


def _whisper_model(folder: str, device: str, compute_type: str, threads: int) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(folder, device=device, compute_type=compute_type, cpu_threads=threads)


def _batched_pipeline(model: Any) -> Any:
    from faster_whisper import BatchedInferencePipeline

    return BatchedInferencePipeline(model=model)


def nvidia_dll_folders() -> list[Path]:
    """The bin folders of NVIDIA's pip packages (nvidia-cublas-cu12 etc.), if installed."""
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return []
    folders: list[Path] = []
    for root in spec.submodule_search_locations:
        folders += sorted(p for p in Path(root).glob("*/bin") if p.is_dir())
    return folders


_nvidia_ready = False


def use_nvidia_files() -> None:
    """Let Windows find the NVIDIA files when ctranslate2 asks for them. Safe to call twice."""
    global _nvidia_ready
    if _nvidia_ready or os.name != "nt":
        return
    _nvidia_ready = True
    for folder in nvidia_dll_folders():
        os.add_dll_directory(str(folder))
        # ctranslate2 loads cuBLAS late, by name, which only looks at PATH.
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


# Set once the graphics card has failed in this run. It is never tried again
# until the app restarts: a second try after a failure can hang ctranslate2.
_gpu_failed = False


def cublas_loadable() -> bool:
    """Whether NVIDIA's cuBLAS file can be loaded. Without it the card can't be used,
    so it isn't even tried (the installed app leaves these big files out)."""
    if os.name != "nt":
        return True
    use_nvidia_files()
    import ctypes

    try:
        ctypes.WinDLL("cublas64_12.dll")
    except OSError:
        return False
    return True


def _cuda_devices() -> int:
    try:
        if not cublas_loadable():
            return 0
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # noqa: BLE001 - no CUDA at all
        return 0


class Transcriber:
    """Loads the model once and transcribes files one after another."""

    def __init__(
        self,
        model_dir: Path,
        model_id: str,
        device: str = "auto",
        factory: ModelFactory = _whisper_model,
        cuda_devices: Callable[[], int] = _cuda_devices,
        batcher: Callable[[Any], Any] = _batched_pipeline,
    ) -> None:
        self.model_dir = model_dir
        self.model_id = model_id
        self.wanted_device = device
        self._factory = factory
        self._cuda_devices = cuda_devices
        self._batcher = batcher
        self._model: Any = None
        self._unbatched: Any = None
        self.device_used: str | None = None

    @property
    def source(self) -> str:
        return f"whisper-{self.model_id}"

    def _load(self) -> Any:
        global _gpu_failed
        if self._model is not None:
            return self._model
        threads = max(1, (os.cpu_count() or 4) // 2)
        if self.wanted_device == "auto" and not _gpu_failed and self._cuda_devices() > 0:
            try:
                model = self._factory(str(self.model_dir), "cuda", "float16", threads)
                # Run it once: missing NVIDIA files only show up when it's used.
                import numpy as np

                segments, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="en")
                list(segments)
                self._model, self.device_used = self._batcher(model), "gpu"
                self._unbatched = model
                return self._model
            except Exception:  # noqa: BLE001 - fall back to the processor
                _gpu_failed = True
        self._model = self._factory(str(self.model_dir), "cpu", "int8", threads)
        self.device_used = "cpu"
        return self._model

    def transcribe(self, path: Path, check: Callable[[], None] | None = None) -> Transcript:
        audio = decode_audio(path)
        model = self._load()
        options: dict[str, Any] = {
            "vad_filter": True,  # skip silence and music-only parts
            "beam_size": 5,
            "temperature": [0.0, 0.4],  # retry a bad line once, not five times
            "condition_on_previous_text": False,  # stops one mistake repeating
        }
        if self.device_used == "gpu":
            options["batch_size"] = GPU_BATCH_SIZE
        try:
            first = self._listen(model, audio, options, check)
        except RuntimeError as error:
            if "No clip timestamps found" not in str(error):
                raise
            first = Transcript("", None, no_speech=True)
        if not first.no_speech or len(audio) > SAMPLE_RATE * SECOND_PASS_SECONDS:
            return first
        if check:
            check()
        # Whisper's voice filter can skip quiet dialogue or dialogue over music.
        # A second pass on short clips checks the original audio with stricter
        # segment confidence to keep music from turning into invented words.
        options.pop("batch_size", None)
        options["vad_filter"] = False
        return self._listen(self._unbatched or model, audio, options, check, strict=True)

    def _listen(
        self, model: Any, audio: Any, options: dict[str, Any],
        check: Callable[[], None] | None, *, strict: bool = False,
    ) -> Transcript:
        segments, info = model.transcribe(audio, **options)
        language = getattr(info, "language", None)
        confidence = float(getattr(info, "language_probability", 1.0) or 0.0)
        # Language confidence is often low for short speech. Let reliable
        # segments establish that speech exists, without guessing a language.
        text = keep_segments(segments, check, strict=strict or confidence < MIN_LANGUAGE_CONFIDENCE)
        if not _has_words(text):
            return Transcript("", None, no_speech=True)
        if confidence < MIN_LANGUAGE_CONFIDENCE:
            language = None
        return Transcript(text, language, no_speech=False)

    def close(self) -> None:
        self._model = None
        self._unbatched = None
