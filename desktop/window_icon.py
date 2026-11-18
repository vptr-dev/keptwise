"""Show the Keptwise logo in the Windows taskbar and Alt+Tab.

Two things decide the taskbar icon on Windows:
1. The "app id" of the process. When the app runs from source, the process is
   python.exe, so without its own id Windows groups the window under Python
   and shows Python's icon.
2. The window's own icon (WM_SETICON). pywebview gives its window the icon of
   the program that started it, which again is Python's when run from source.
Both are set here. Nothing happens on macOS or Linux.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

APP_ID = "Keptwise.Desktop"

WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010


def set_app_id() -> None:
    """Call before the window opens."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass  # very old Windows: the icon is just Python's


def _window_handle(window: Any, title: str) -> int:
    """The window's Windows handle: from pywebview if it says, else by title."""
    import ctypes

    native = getattr(window, "native", None)
    handle = getattr(native, "Handle", None)
    if handle is not None:
        try:
            return int(handle.ToInt64())
        except (AttributeError, TypeError, ValueError):
            pass
    return int(ctypes.windll.user32.FindWindowW(None, title) or 0)


def set_window_icon(window: Any, title: str, icon: Path) -> bool:
    """Give the open window the logo as its big (taskbar, Alt+Tab) and small
    (corner) icon. Returns False if it couldn't."""
    if sys.platform != "win32" or not icon.exists():
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        hwnd = _window_handle(window, title)
        if not hwnd:
            return False
        big_size = max(48, user32.GetSystemMetrics(11) * 2)  # SM_CXICON, sharp on high-DPI screens
        small_size = max(16, user32.GetSystemMetrics(49))  # SM_CXSMICON
        big = user32.LoadImageW(None, str(icon), IMAGE_ICON, big_size, big_size, LR_LOADFROMFILE)
        small = user32.LoadImageW(None, str(icon), IMAGE_ICON, small_size, small_size, LR_LOADFROMFILE)
        if big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
        if small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
        return bool(big or small)
    except (AttributeError, OSError):
        return False
