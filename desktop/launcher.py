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

Only one window at a time: starting it again while it's open just brings
the open window to the front (single_instance.py).
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
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
import single_instance  # noqa: E402
from workspaces import Workspaces
import window_frame  # noqa: E402
from window_icon import set_app_id, set_window_icon  # noqa: E402

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
    """F11 uses the native window's fullscreen transition."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._fullscreen_lock = threading.Lock()
        self._maximize_on_exit = False
        self._frame = None
        self._spaces = None
        self._services = None
        self._reopen = False

    def workspaces(self):
        return self._spaces.list()

    def create_workspace(self, name):
        return self._spaces.create(name)

    def open_workspace(self, key):
        with self._fullscreen_lock:
            if self._reopen or key == self._spaces.current:
                return
            with self._services.db.connect() as conn:
                if conn.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','paused') LIMIT 1").fetchone():
                    raise ValueError("Finish or cancel running jobs before switching workspace.")
            self._spaces.choose(key)
            self._reopen = True
            self._window.destroy()

    def info(self) -> dict[str, bool]:
        native = getattr(self._window, "native", None)
        return {
            "integrated": self._frame is not None,
            "maximized": str(getattr(native, "WindowState", "")) == "Maximized",
            "fullscreen": bool(getattr(native, "is_fullscreen", False)),
        }

    def caption(self, action: str) -> None:
        window = self._window
        state = self.info()
        if window is None or not state["integrated"] or state["fullscreen"]:
            return
        if action == "move":
            window_frame.begin_drag(window)
        elif action == "minimize":
            window.minimize()
        elif action == "maximize":
            (window.restore if state["maximized"] else window.maximize)()
        elif action == "close":
            window.destroy()

    def toggle_fullscreen(self) -> None:
        window = self._window
        if window is None:
            return
        with self._fullscreen_lock:
            native = getattr(window, "native", None)
            if getattr(native, "is_fullscreen", False):
                window.toggle_fullscreen()
                if self._maximize_on_exit:
                    window.maximize()
                self._maximize_on_exit = False
                return

            self._maximize_on_exit = str(getattr(native, "WindowState", "")) == "Maximized"
            # WinForms remembers the bounds it sees on entry and always exits
            # to Normal. Give it the restored bounds, then reapply maximize on exit.
            if self._maximize_on_exit:
                window.restore()
            window.toggle_fullscreen()


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
    from app.paths import default_data_dir
    from app.ai.secrets import KeyringStore
    from app.services import build_services

    root = args.data_dir or default_data_dir()
    if not args.serve_only:
        if not single_instance.claim(root):
            # Already open: show that window instead of opening a second one.
            print("Keptwise is already open; bringing its window to the front.")
            single_instance.show_existing(WINDOW_TITLE)
            return 0
    spaces = Workspaces(root)
    send_output_to_log(spaces.directory)
    if FROZEN:
        from app.updater import clean_downloads

        clean_downloads()  # the installer of an update that has now finished
    token = args.token or secrets.token_urlsafe(32)
    app = create_app(session_token=token, static_dir=FRONTEND_DIST, app_services=build_services(spaces.directory, keys=KeyringStore(spaces.current)))
    services = app.state.services
    if args.serve_only:
        try:
            return serve_only(app, args.port or 8765, token)
        finally:
            services.shutdown()

    controls = WindowControls()
    sock = open_local_socket()
    base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = BackendServer(app, sock)
    server.start()
    try:
        wait_until_ready(base_url)
        print(f"Keptwise {__version__} is running at {base_url}")
        # Let Windows manage resizing, moving and snapping.
        set_app_id()  # the taskbar shows Keptwise, not Python
        controls._spaces = spaces
        controls._services = services
        window = webview.create_window(
            WINDOW_TITLE,
            url=f"{base_url}/session/start?token={token}",
            width=1200,
            height=800,
            min_size=(680, 480),
            resizable=True,
            # Without this, pywebview cancels every drag that starts on a link
            # or picture, which breaks dragging sidebar pages, folders and saves.
            draggable=True,
            js_api=controls,
        )
        controls._window = window  # noqa: SLF001 - kept private so the page can't see it

        def quit_for_update() -> None:
            # The one-click update: stop the jobs, then end the process at once.
            # (Closing the window from this thread could crash in pywebview.)
            services.shutdown()
            os._exit(0)

        services.extras["quit_app"] = quit_for_update
        def shown() -> None:
            set_window_icon(window, WINDOW_TITLE, ICON_FILE)
            try:
                controls._frame = window_frame.install(window)
            except Exception as error:  # Keep the Windows frame if integration is unsupported.
                print(f"Using the Windows window frame: {error}")
            try:
                window.evaluate_js("window.dispatchEvent(new Event('keptwise-frame'))")
            except Exception:
                pass  # The page also reads the state when the bridge becomes ready.

        window.events.shown += shown
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
        single_instance.release()
        if controls._reopen:
            command = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
            subprocess.Popen([*command, *sys.argv[1:]], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


if __name__ == "__main__":
    sys.exit(main())
