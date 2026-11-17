# PyInstaller recipe for Keptwise.exe (a "one-folder" build).
#
# Don't run this by hand: packaging\build.ps1 runs it with the right settings.
# It reads two environment variables that build.ps1 sets:
#   SK_SEARCH_MODEL  folder with the bge-small-en-v1.5 search model (5 files)
#   SK_FFMPEG        optional: path to an ffmpeg.exe to ship next to the app
#
# Result: build\app\Keptwise\Keptwise.exe plus an "_internal" folder.
# The NVIDIA speed-up files (backend\requirements-gpu.txt, about 600 MB) are
# left out on purpose: speech to text uses the processor in the installed app.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is set by PyInstaller
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from app import __version__  # noqa: E402

# ---------- version info shown in the file's Properties -> Details ----------

numbers = [int(part) for part in __version__.split(".")[:3] if part.isdigit()]
numbers = (numbers + [0, 0, 0])[:3] + [0]
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=tuple(numbers), prodvers=tuple(numbers)),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", "Keptwise"),
                StringStruct("FileDescription", "Keptwise"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "Keptwise"),
                StringStruct("LegalCopyright", "Open source. See LICENSE."),
                StringStruct("OriginalFilename", "Keptwise.exe"),
                StringStruct("ProductName", "Keptwise"),
                StringStruct("ProductVersion", __version__),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

# ---------- files that go inside ----------

datas = [(str(ROOT / "frontend" / "dist"), "frontend_dist")]
datas.append((str(ROOT / "desktop" / "icon.ico"), "."))  # the window's taskbar icon
search_model = Path(os.environ["SK_SEARCH_MODEL"])
datas.append((str(search_model), "models/search/bge-small-en-v1.5"))
datas += collect_data_files("faster_whisper")  # the voice detector model (silero_vad)
datas += collect_data_files("fastembed")
datas += collect_data_files("yt_dlp")
datas += collect_data_files("certifi")

binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
ffmpeg = os.environ.get("SK_FFMPEG")
if ffmpeg:
    binaries.append((ffmpeg, "ffmpeg"))  # app.enrich.fetch.bundled_ffmpeg finds it here

hiddenimports = []
hiddenimports += collect_submodules("app")  # the backend (some parts load lazily)
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("yt_dlp.extractor")
hiddenimports += collect_submodules("keyring.backends")
hiddenimports += ["logo_art"]  # drawn at run time for the taskbar icon
hiddenimports += ["faster_whisper", "fastembed", "ctranslate2", "av", "tokenizers", "py_rust_stemmers"]

excludes = [
    "nvidia",  # GPU files: optional, far too big for the default installer
    "pytest", "_pytest", "httpx2", "httpcore2",  # test-only
    "tkinter", "matplotlib", "IPython", "jupyter", "notebook",
    "PyInstaller",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Keptwise",
    icon=str(ROOT / "desktop" / "icon.ico"),
    version=version_info,
    console=False,  # a window app: no black console box
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="Keptwise",
    upx=False,
)
