"""Let other programs go first while the app transcribes.

Transcribing keeps the processor busy for a long time. While it runs, the
app's process gets "below normal" priority on Windows, so games, Blender
and the rest of the PC stay smooth; the transcripts just take a bit longer.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

NORMAL_PRIORITY_CLASS = 0x0020
BELOW_NORMAL_PRIORITY_CLASS = 0x4000


@contextmanager
def background_priority() -> Iterator[None]:
    if sys.platform != "win32":
        yield
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    process = kernel32.GetCurrentProcess()
    before = kernel32.GetPriorityClass(process) or NORMAL_PRIORITY_CLASS
    kernel32.SetPriorityClass(process, BELOW_NORMAL_PRIORITY_CLASS)
    try:
        yield
    finally:
        kernel32.SetPriorityClass(process, before)
