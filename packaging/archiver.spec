# PyInstaller spec for File Archiver (Windows onedir build).
#
# Build with:  pyinstaller packaging/archiver.spec --noconfirm
#
# Produces a "onedir" bundle (dist/FileArchiver/) rather than a single
# --onefile exe: with ~2 GB of embedded tools + the Whisper model, a
# onefile build would have to re-extract everything into a temp folder on
# *every* launch, which is slow and wastes disk space. The onedir folder
# is what "portable" refers to in BUILD.md - zip it up and it runs
# anywhere without an installer. FileArchiver.exe inside that folder is
# still a single, self-contained, immediately runnable executable.

import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).parent
PACKAGING = Path(SPECPATH)

datas = [
    (str(ROOT / "archiver" / "web" / "templates"), "archiver/web/templates"),
    (str(ROOT / "archiver" / "web" / "static"), "archiver/web/static"),
    (str(PACKAGING / "config.default.yaml"), "."),
    (str(PACKAGING / "fetch_whisper_model.ps1"), "."),
]

# Bundled external tools (Tesseract, FFmpeg, Poppler, qpdf) + Ghostscript
# (kept in its own subfolder because it needs its bin/lib/Resource layout
# preserved relative to the executable).
#
# The Whisper model is deliberately EXCLUDED here and shipped as a
# separate release asset (whisper-medium-model.zip) instead of being
# baked into this bundle: at ~1.5 GB it would push a single onefile/
# installer artifact over GitHub's 2 GB release-asset limit. The installer
# and fetch_whisper_model.ps1 (for portable use) download and place it
# into tools/whisper-medium next to this executable after the fact.
tools_dir = PACKAGING / "tools"
if tools_dir.is_dir():
    for item in tools_dir.iterdir():
        if item.name == "whisper-medium":
            continue
        datas.append((str(item), f"tools/{item.name}"))

hiddenimports = [
    "faster_whisper",
    "ctranslate2",
    "ocrmypdf",
    "ocrmypdf.builtin_plugins",
    "pytesseract",
    "pdf2image",
    "fitz",
    "docx",
    "yaml",
]

a = Analysis(
    [str(PACKAGING / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileArchiver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Kept as a console app: this is a CLI tool at heart (scan/analyze/serve
    # commands), and disabling the console would silently swallow all
    # typer.echo() output and error messages, including when the web UI is
    # started by double-click. A console window is the accepted trade-off
    # for keeping both usage modes fully functional; see BUILD.md.
    console=True,
    icon=str(PACKAGING / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="FileArchiver",
)
