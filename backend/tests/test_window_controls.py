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


def test_the_taskbar_icon_can_take_the_accent_colour(tmp_path: Path) -> None:
    from PIL import Image

    from window_icon import tinted_icon

    plain = Path(__file__).resolve().parents[2] / "desktop" / "icon.ico"
    assert tinted_icon(plain, "default", True, tmp_path) == plain  # white front, as drawn
    assert tinted_icon(plain, "nonsense", True, tmp_path) == plain
    teal = tinted_icon(plain, "teal", False, tmp_path)
    assert teal == tmp_path / "icon-teal.ico"
    with Image.open(teal) as picture:
        r, g, b, _ = picture.convert("RGBA").getpixel((170, 160))  # on the front bookmark (256 px)
    assert g > r and b > r  # teal, not grey
    assert WindowControls().set_accent("teal", True) is False  # no window: nothing to do
