"""Keep the Windows resize frame and put the caption inside Keptwise."""

from __future__ import annotations

import sys
from typing import Any


def install(window: Any) -> Any:
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
