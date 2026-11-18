"""Only one Keptwise window at a time.

Opening Keptwise while it's already open brings the open window to the
front (restored if it was minimised) instead of starting a second copy.
Two copies would share one data folder and get in each other's way.

A named Windows mutex marks "Keptwise is running for this data folder"
(the name includes the folder, so a developer copy with its own data can
run beside the installed app). Windows frees it when the process ends,
even after a crash, so a stale lock can never keep the app from starting.
Nothing happens on macOS or Linux.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

_held: list[int] = []  # the mutex handle, kept open for the life of the process


def lock_name(data_dir: Path) -> str:
    folder = str(data_dir.resolve()).lower()
    return "Local\\Keptwise-" + hashlib.sha1(folder.encode("utf-8")).hexdigest()[:16]


def claim(data_dir: Path) -> bool:
    """True if this is the only Keptwise for this data folder (it now holds
    the lock); False if another one already runs."""
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle = kernel32.CreateMutexW(None, False, lock_name(data_dir))
    if not handle:
        return True  # can't tell: better to open than to refuse
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _held.append(handle)
    return True


def release() -> None:
    """Let go of the lock (the process ending does this too)."""
    if sys.platform != "win32":
        return
    import ctypes

    while _held:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_held.pop()))


def show_existing(title: str, wait_s: float = 5.0) -> bool:
    """Bring the open Keptwise window to the front. It may still be starting,
    so look for a few seconds. Returns whether it was found."""
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    deadline = time.monotonic() + wait_s
    while True:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            if user32.IsIconic(ctypes.c_void_p(hwnd)):
                user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
            user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)
