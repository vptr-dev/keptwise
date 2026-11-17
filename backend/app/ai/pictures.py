"""Pictures from a video, so the AI can look at what it shows and not only
read what was said (on-screen text, the place, the dish, the product).

While a video's file is on the computer for its transcript, a few stills are
kept next to its cover picture (thumbnails\\<id>-f1.jpg ...). Videos that
were transcribed before this existed only have the cover picture; that is
used instead. Pictures are shrunk before they go to the AI, so they cost
little time.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

FRAMES = 3
MAX_SIDE = 512  # pixels, the longer side of what the AI is sent
QUALITY = 78


def frame_paths(folder: Path, item_id: int) -> list[Path]:
    return sorted(folder.glob(f"{item_id}-f*.jpg"))


def capture_frames(media: Path, folder: Path, item_id: int, count: int = FRAMES) -> int:
    """Save a few stills spread across the video. Returns how many were
    saved. Never raises: a video without pictures (or one that can't be
    read) just gets none."""
    try:
        import av  # imported here so the app starts without loading it

        saved = 0
        with av.open(str(media)) as container:
            if not container.streams.video:
                return 0
            stream = container.streams.video[0]
            length = float(container.duration or 0) / av.time_base  # seconds
            for number in range(1, count + 1):
                # Not the very start or end: those are often a logo or a black frame.
                at = length * number / (count + 1) if length > 0 else 0.0
                container.seek(int(at * av.time_base), backward=True, any_frame=False)
                for frame in container.decode(stream):
                    image = frame.to_image()
                    image.thumbnail((MAX_SIDE, MAX_SIDE))
                    image.convert("RGB").save(folder / f"{item_id}-f{number}.jpg", "JPEG", quality=QUALITY)
                    saved += 1
                    break
                if length <= 0:
                    break  # unknown length: one picture is all we can find
        return saved
    except Exception:  # noqa: BLE001 - pictures are a bonus, never a reason to fail
        return 0


def _encoded(path: Path) -> str | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=QUALITY)
        return base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def pictures_for(folder: Path, item_id: int, thumbnail_name: str | None, limit: int = FRAMES) -> list[str]:
    """The pictures to show the AI for one video, as base64 JPEGs: its
    stills when there are any, else its cover picture."""
    paths = frame_paths(folder, item_id)[:limit]
    if not paths and thumbnail_name:
        cover = (folder / thumbnail_name).resolve()
        if cover.is_relative_to(folder.resolve()) and cover.is_file():
            paths = [cover]
    return [data for data in (_encoded(path) for path in paths) if data]
