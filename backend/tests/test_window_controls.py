"""The app's own window buttons (desktop/launcher.py), with a fake window."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))

from launcher import WindowControls  # noqa: E402


class FakeWindow:
    def __init__(self) -> None:
        self.native = SimpleNamespace(WindowState="Normal")
        self.width, self.height = 1200, 800
        self.calls: list[str] = []

    def maximize(self) -> None:
        self.calls.append("maximize")
        self.native.WindowState = "Maximized"

    def restore(self) -> None:
        self.calls.append("restore")
        self.native.WindowState = "Normal"

    def minimize(self) -> None:
        self.calls.append("minimize")

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height

    def destroy(self) -> None:
        self.calls.append("destroy")


def controls_with(window: FakeWindow) -> WindowControls:
    controls = WindowControls()
    controls._window = window  # type: ignore[assignment]
    return controls


def test_maximise_restore_follow_the_real_window_state() -> None:
    window = FakeWindow()
    controls = controls_with(window)
    assert controls.toggle_maximize() is True
    assert controls.toggle_maximize() is False
    window.native.WindowState = "Maximized"  # e.g. maximised with Win+Up
    assert controls.is_maximized() is True
    assert controls.toggle_maximize() is False
    assert window.calls == ["maximize", "restore", "restore"]


def test_resize_keeps_a_minimum_and_skips_when_maximised() -> None:
    window = FakeWindow()
    controls = controls_with(window)
    controls.resize(300, 200)
    assert (window.width, window.height) == (WindowControls.MIN_WIDTH, WindowControls.MIN_HEIGHT)
    controls.resize(1000.6, 700.2)
    assert controls.size() == [1000, 700]
    window.native.WindowState = "Maximized"
    controls.resize(1300, 900)
    assert controls.size() == [1000, 700]


def test_buttons_do_nothing_before_the_window_exists() -> None:
    controls = WindowControls()
    controls.minimize()
    controls.close()
    assert controls.toggle_maximize() is False and controls.size() == [0, 0]


def test_page_only_sees_the_button_actions() -> None:
    public = {name for name in dir(WindowControls) if not name.startswith("_") and callable(getattr(WindowControls, name))}
    assert public == {"minimize", "toggle_maximize", "is_maximized", "close", "size", "resize", "set_accent"}


def test_the_taskbar_icon_is_the_plain_white_logo_with_no_tile(tmp_path: Path) -> None:
    from PIL import Image

    plain = Path(__file__).resolve().parents[2] / "desktop" / "icon.ico"
    with Image.open(plain) as picture:
        big = picture.convert("RGBA")
        r, g, b, _ = big.getpixel((170, 160))  # on the front bookmark (256 px)
        corner = big.getpixel((3, 3))
    assert min(r, g, b) > 230  # white
    assert corner[3] == 0  # no dark tile behind it
    assert WindowControls().set_accent("teal", True) is False  # no window: nothing to do
