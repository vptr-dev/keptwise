"""Starts Keptwise: the backend server plus the app window.

What happens, step by step:
1. Open a network socket on a free port of 127.0.0.1 (this PC only) and
   make a random session token.
2. Start the backend (FastAPI + uvicorn) on that socket in a background
   thread. The window needs the main thread, so the server can't have it.
3. Wait until the backend answers /api/health.
4. Open the app window at /session/start?token=..., which saves the token
   in a cookie and then shows the home page.
5. When the window closes, stop the backend and exit.

Run it:      .\\.venv\\Scripts\\python.exe desktop\\launcher.py
Self-check:  add --smoke-test to open the window, check the hello page
             appears, close the window, and exit with code 0 (pass) or 1.
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# FROZEN: running as the installed Keptwise.exe (built by PyInstaller,
# see packaging/). Its files then sit in the "_internal" folder (sys._MEIPASS).
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    FRONTEND_DIST = BUNDLE_DIR / "frontend_dist"
    ICON_FILE = BUNDLE_DIR / "icon.ico"
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
    ICON_FILE = REPO_ROOT / "desktop" / "icon.ico"
    # Let Python find the backend's "app" package.
    sys.path.insert(0, str(REPO_ROOT / "backend"))

import uvicorn  # noqa: E402
import webview  # noqa: E402

from app import __version__  # noqa: E402
from app.main import create_app  # noqa: E402
from window_icon import set_app_id, set_window_icon, tinted_icon  # noqa: E402

WINDOW_TITLE = "Keptwise"
# The hello page shows this once it has talked to the backend.
SMOKE_TEST_TEXT = "Backend connected"


def open_local_socket() -> socket.socket:
    """Open a socket on 127.0.0.1 with a free port picked by Windows.

    Keeping the socket open (instead of just asking for a free port number)
    means no other program can grab the port before the server starts.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


class BackendServer:
    """Runs uvicorn in a background thread, with a clean stop()."""

    def __init__(self, app: object, sock: socket.socket) -> None:
        # access_log=False: request lines would include the session token.
        config = uvicorn.Config(app, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [sock]}, daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


def wait_until_ready(base_url: str, timeout: float = 15.0) -> None:
    """Poll /api/health until the server answers, or raise after timeout."""
    # An empty ProxyHandler skips any proxy set up in Windows: 127.0.0.1
    # must always be reached directly.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(f"{base_url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass  # not up yet
        time.sleep(0.1)
    raise RuntimeError(f"The backend did not start within {timeout:.0f} seconds.")


def run_smoke_test(window: webview.Window, result: dict[str, bool]) -> None:
    """Runs alongside the window: wait for the hello page, then close it."""
    try:
        if not window.events.loaded.wait(timeout=20):
            print("Smoke test: the page never finished loading.")
            return
        # The page asks the backend for the hello message after it loads,
        # so give it a few seconds to show up.
        text = ""
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            text = str(window.evaluate_js("document.body.innerText") or "")
            if SMOKE_TEST_TEXT in text:
                result["ok"] = True
                print("Smoke test passed. The window shows:")
                print("  " + " | ".join(line for line in text.splitlines() if line))
                return
            time.sleep(0.25)
        print(f"Smoke test failed. The window shows: {text!r}")
    finally:
        window.destroy()


class WindowControls:
    """The app draws its own title bar (minimise, maximise, close, and the
    resize handles), because the window has no Windows title bar. The page
    calls these through window.pywebview.api."""

    MIN_WIDTH, MIN_HEIGHT = 800, 600

    def __init__(self) -> None:
        # Underscores: these aren't shown to the page. launcher.main sets _window.
        self._window: webview.Window | None = None
        self._maximized = False  # only used where Windows can't be asked

    def _is_maximized_now(self) -> bool:
        """Ask Windows whether the window is maximised (it can also change by
        Win+Up, or by dragging the window to the top of the screen)."""
        state = getattr(getattr(self._window, "native", None), "WindowState", None)
        return str(state) == "Maximized" if state is not None else self._maximized

    def _keep_taskbar_visible(self) -> None:
        """A window without a title bar would cover the taskbar when maximised.
        Limit it to the screen's work area (Windows only; elsewhere do nothing)."""
        form = getattr(self._window, "native", None)
        if form is None or not hasattr(form, "MaximizedBounds"):
            return
        try:
            from System import Action  # type: ignore[import-not-found]
            from System.Drawing import Rectangle  # type: ignore[import-not-found]
            from System.Windows.Forms import Screen  # type: ignore[import-not-found]

            def apply() -> None:
                screen = Screen.FromControl(form)
                work, whole = screen.WorkingArea, screen.Bounds
                # The position counts from the screen's own corner.
                form.MaximizedBounds = Rectangle(work.X - whole.X, work.Y - whole.Y, work.Width, work.Height)

            form.Invoke(Action(apply))
        except Exception as error:  # noqa: BLE001 - never stop the button working
            print(f"Couldn't fit the window to the work area: {error}")

    def set_accent(self, accent: str, dark: bool) -> bool:
        """The page tells us its accent colour and theme, so the icon in the
        taskbar and Alt+Tab can match it."""
        if self._window is None or not isinstance(accent, str):
            return False
        import tempfile

        icon = tinted_icon(ICON_FILE, accent[:20], bool(dark), Path(tempfile.gettempdir()) / "Keptwise-icons")
        return set_window_icon(self._window, WINDOW_TITLE, icon)

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def toggle_maximize(self) -> bool:
        """Maximise, or go back to the normal size. Returns True if now maximised."""
        if self._window:
            if self._is_maximized_now():
                self._window.restore()
                self._maximized = False
            else:
                self._keep_taskbar_visible()
                self._window.maximize()
                self._maximized = True
        return self._is_maximized_now()

    def is_maximized(self) -> bool:
        return self._is_maximized_now()

    def close(self) -> None:
        if self._window:
            self._window.destroy()

    def size(self) -> list[int]:
        return [self._window.width, self._window.height] if self._window else [0, 0]

    def resize(self, width: float, height: float) -> None:
        """Called while the user drags the window's right or bottom edge."""
        if self._window and not self._is_maximized_now():
            self._window.resize(max(self.MIN_WIDTH, int(width)), max(self.MIN_HEIGHT, int(height)))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Keptwise.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="open the window, check the hello page appears, then close",
    )
    # Developer options: run only the backend, to open it in a normal browser.
    parser.add_argument("--serve-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--token", default="", help=argparse.SUPPRESS)
    parser.add_argument("--data-dir", type=Path, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def serve_only(app: object, port: int, token: str) -> int:
    """Run just the backend (no window) until Ctrl+C. For developers."""
    print(f"Open http://127.0.0.1:{port}/session/start?token={token}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    return 0


def send_output_to_log(data_dir: Path | None) -> None:
    """The installed app has no console window, so print() and error
    messages would go nowhere (and some libraries crash without one).
    Write them to app.log in the "logs" folder of the data folder instead, kept small."""
    # The installed app always logs to the file (PyInstaller gives a window
    # app a stand-in output that throws everything away).
    if not FROZEN and sys.stdout is not None and sys.stderr is not None:
        return
    from app.paths import default_data_dir

    logs = (data_dir or default_data_dir()) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_file = logs / "app.log"
    if log_file.exists() and log_file.stat().st_size > 2_000_000:
        log_file.replace(logs / "app.old.log")
    stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - open for the app's lifetime
    sys.stdout = stream
    sys.stderr = stream


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    send_output_to_log(args.data_dir)
    if FROZEN:
        from app.updater import clean_downloads

        clean_downloads()  # the installer of an update that has now finished
    token = args.token or secrets.token_urlsafe(32)
    app = create_app(session_token=token, static_dir=FRONTEND_DIST, data_dir=args.data_dir)
    services = app.state.services
    if args.serve_only:
        try:
            return serve_only(app, args.port or 8765, token)
        finally:
            services.shutdown()

    sock = open_local_socket()
    base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = BackendServer(app, sock)
    server.start()
    try:
        wait_until_ready(base_url)
        print(f"Keptwise {__version__} is running at {base_url}")
        # No Windows title bar: the app's own top bar has the buttons and is
        # where the window is dragged from. Only elements marked with the
        # "pywebview-drag-region" class drag it, not the buttons inside them.
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
        set_app_id()  # the taskbar shows Keptwise, not Python
        controls = WindowControls()
        window = webview.create_window(
            WINDOW_TITLE,
            url=f"{base_url}/session/start?token={token}",
            width=1200,
            height=800,
            min_size=(WindowControls.MIN_WIDTH, WindowControls.MIN_HEIGHT),
            frameless=True,
            easy_drag=False,
            # Without this, pywebview cancels every drag that starts on a link
            # or picture, which breaks dragging sidebar pages, folders and saves.
            draggable=True,
            shadow=True,
            js_api=controls,
        )
        controls._window = window  # noqa: SLF001 - kept private so the page can't see it

        def quit_for_update() -> None:
            # The one-click update: stop the jobs, then end the process at once.
            # (Closing the window from this thread could crash in pywebview.)
            services.shutdown()
            os._exit(0)

        services.extras["quit_app"] = quit_for_update
        window.events.shown += lambda: set_window_icon(window, WINDOW_TITLE, ICON_FILE)
        # private_mode: the window keeps no cookies or cache after it closes.
        if args.smoke_test:
            result: dict[str, bool] = {}
            webview.start(run_smoke_test, (window, result), private_mode=True)
            return 0 if result.get("ok") else 1
        webview.start(private_mode=True)
        return 0
    finally:
        services.shutdown()  # stop background jobs first, so the server can close
        server.stop()
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
