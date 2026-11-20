"""The native window's fullscreen bridge and taskbar icon."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))

from launcher import WindowControls  # noqa: E402


def test_fullscreen_uses_the_native_window_transition() -> None:
    controls = WindowControls()
    controls.toggle_fullscreen()  # safe when the window hasn't been created
    native_toggle = Mock()
    controls._window = SimpleNamespace(toggle_fullscreen=native_toggle)  # type: ignore[assignment]
    controls.toggle_fullscreen()
    native_toggle.assert_called_once_with()


def test_fullscreen_restores_a_maximized_window_to_maximized() -> None:
    controls = WindowControls()
    native = SimpleNamespace(is_fullscreen=False, WindowState="Maximized")
    window = Mock(native=native)
    controls._window = window
    window.toggle_fullscreen.side_effect = lambda: setattr(native, "is_fullscreen", not native.is_fullscreen)

    controls.toggle_fullscreen()
    controls.toggle_fullscreen()

    assert [call[0] for call in window.method_calls] == ["restore", "toggle_fullscreen", "toggle_fullscreen", "maximize"]


def test_fullscreen_is_the_only_window_action_exposed_to_the_page() -> None:
    public = {name for name in dir(WindowControls) if not name.startswith("_") and callable(getattr(WindowControls, name))}
    assert public == {"toggle_fullscreen"}


def test_the_taskbar_icon_is_the_plain_white_logo_with_no_tile() -> None:
    from PIL import Image

    plain = Path(__file__).resolve().parents[2] / "desktop" / "icon.ico"
    with Image.open(plain) as picture:
        big = picture.convert("RGBA")
        r, g, b, _ = big.getpixel((170, 160))  # on the front bookmark (256 px)
        corner = big.getpixel((3, 3))
    assert min(r, g, b) > 230  # white
    assert corner[3] == 0  # no dark tile behind it
