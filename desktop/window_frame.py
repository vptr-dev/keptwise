"""Keep the Windows resize frame and put the caption inside Keptwise."""

from __future__ import annotations

import sys
from typing import Any


UNSAVE_HOTKEY_ID = 1
UNSAVE_CHORDS = {"ctrl-alt-u": (0x0003, ord("U")), "ctrl-alt-n": (0x0003, ord("N")), "ctrl-shift-f9": (0x0006, 0x78)}


def install(window: Any, on_unsave_hotkey=None) -> Any:
    if sys.platform != "win32" or window.native is None:
        return None
    import ctypes
    from ctypes.wintypes import HWND, POINT, RECT, UINT
    from System import Action  # type: ignore[import-not-found]

    user = ctypes.windll.user32
    control = ctypes.windll.comctl32
    ptr = ctypes.c_size_t
    result_type = ctypes.c_ssize_t
    proc_type = ctypes.WINFUNCTYPE(result_type, HWND, UINT, ptr, result_type, ptr, ptr)
    control.SetWindowSubclass.argtypes = [HWND, proc_type, ptr, ptr]
    control.DefSubclassProc.argtypes = [HWND, UINT, ptr, result_type]
    control.DefSubclassProc.restype = result_type
    user.GetWindowLongW.argtypes = [HWND, ctypes.c_int]
    user.GetDpiForWindow.argtypes = [HWND]
    user.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, UINT]
    user.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT]

    @proc_type
    def frame(hwnd, message, wparam, lparam, subclass_id, ref):
        if message == 0x0312 and wparam == UNSAVE_HOTKEY_ID and on_unsave_hotkey:  # WM_HOTKEY
            on_unsave_hotkey()
            return 0
        caption = user.GetWindowLongW(hwnd, -16) & 0x00C00000 == 0x00C00000  # WS_CAPTION
        if message == 0x0083 and wparam and caption:  # WM_NCCALCSIZE
            rect = RECT.from_address(lparam)  # first rectangle in NCCALCSIZE_PARAMS
            outer_top = rect.top
            result = control.DefSubclassProc(hwnd, message, wparam, lparam)
            dpi = user.GetDpiForWindow(hwnd) or 96
            border = user.GetSystemMetricsForDpi(33, dpi) + user.GetSystemMetricsForDpi(92, dpi)
            # Keep native resize borders and maximized work-area insets on every edge.
            rect.top = min(rect.top, outer_top + border) if user.IsZoomed(HWND(hwnd)) else outer_top
            return result
        result = control.DefSubclassProc(hwnd, message, wparam, lparam)
        if message == 0x0084 and caption and not user.IsZoomed(HWND(hwnd)):
            bounds = RECT()
            user.GetWindowRect(HWND(hwnd), ctypes.byref(bounds))
            x = ctypes.c_short(lparam & 0xffff).value
            y = ctypes.c_short((lparam >> 16) & 0xffff).value
            grip = max(4, round(5 * (user.GetDpiForWindow(hwnd) or 96) / 96))
            if bounds.top <= y < bounds.top + grip:
                return 13 if x < bounds.left + grip else 14 if x >= bounds.right - grip else 12
        if message == 0x0084 and caption and result in (2, 3, 5, 8, 9, 20):  # WM_NCHITTEST
            return 1  # HTCLIENT for the caption and buttons now drawn by Keptwise
        return result

    state = []
    form = window.native

    def apply():
        hwnd = form.Handle.ToInt64()
        if control.SetWindowSubclass(hwnd, frame, 1, 0):
            state.append(frame)
            user.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)  # FRAMECHANGED, no move, size, activation or z-order

    form.Invoke(Action(apply)) if form.InvokeRequired else apply()
    return state[0] if state else None  # caller keeps the native callback alive


def begin_drag(window: Any) -> None:
    """Start a native caption move. Windows handles snapping and drag-to-restore."""
    if sys.platform != "win32" or window.native is None:
        return
    import ctypes
    from ctypes.wintypes import HWND, POINT
    from System import Action  # type: ignore[import-not-found]

    form = window.native

    def start():
        if form.is_fullscreen:
            return
        user = ctypes.windll.user32
        user.ReleaseCapture()
        user.SendMessageW.argtypes = [HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user.SendMessageW.restype = ctypes.c_ssize_t
        point = POINT()
        user.GetCursorPos(ctypes.byref(point))
        coords = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
        user.SendMessageW(form.Handle.ToInt64(), 0x00A1, 2, coords)  # WM_NCLBUTTONDOWN, HTCAPTION

    form.BeginInvoke(Action(start))


def apply_backdrop(window: Any, style: str, dark: bool) -> bool:
    """Apply the selected Win32 backdrop on the window's UI thread."""
    if style not in ("clear", "glass", "mica", "solid"):
        return False
    import ctypes
    from ctypes.wintypes import HWND
    from System.Drawing import Color

    native = window.native
    webview = getattr(native, "webview", None)
    if webview is None or not hasattr(webview, "DefaultBackgroundColor"):
        return False
    hwnd = HWND(native.Handle.ToInt64())
    dwm = ctypes.windll.dwmapi
    theme = ctypes.c_int(bool(dark))
    dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(theme), ctypes.sizeof(theme))
    backdrop = ctypes.c_int({"mica": 2, "glass": 3}.get(style, 1))
    applied = dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop)) == 0
    native_material = applied and style in ("mica", "glass")
    margins = (ctypes.c_int * 4)(*([-1] * 4 if native_material else [0] * 4))
    if dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins)) != 0:
        native_material = False
    native.Opacity = 0.91 if style == "clear" else 1.0
    base = Color.FromArgb(27, 27, 31) if dark else Color.FromArgb(241, 241, 244)
    native.BackColor = Color.Black if native_material else base
    webview.DefaultBackgroundColor = Color.Transparent if native_material else base
    return native_material
