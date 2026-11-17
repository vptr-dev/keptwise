r"""Makes the app's pictures from the logo's shapes (desktop/logo_art.py):

- desktop/icon.ico: the program and installer icon (all Windows sizes)
- frontend/src/assets/logo.png: the window's tab icon (the app draws the
  logo itself, from frontend/src/components/Logo.tsx)

The results are kept in git, so this only needs running again when the logo changes:
    .\.venv\Scripts\python.exe packaging\make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "desktop"))

from logo_art import draw_logo, save_icon  # noqa: E402

ICON = ROOT / "desktop" / "icon.ico"
LOGO = ROOT / "frontend" / "src" / "assets" / "logo.png"

if __name__ == "__main__":
    save_icon(ICON)
    LOGO.parent.mkdir(parents=True, exist_ok=True)
    draw_logo(256).save(LOGO, optimize=True)
    print(f"Saved {ICON} and {LOGO}")
