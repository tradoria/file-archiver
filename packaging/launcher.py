"""PyInstaller entry point for the Windows build of File Archiver.

This is a thin wrapper around the existing ``archiver`` package. It does
not change any scanning/extraction/sorting logic - it only adapts how the
app is *started* and *finds its files* so it works as a frozen, installed
Windows application instead of a script run from a project checkout:

- Bundled resources (templates, tools, whisper model) live next to the
  executable, not in the current working directory.
- Per-user, writable data (config.yaml, artifacts/, archiver.db) lives in
  %LOCALAPPDATA%\\FileArchiver instead of the install directory, which is
  typically read-only for a non-admin user under Program Files.
- Double-clicking the exe (no arguments) starts the web review UI and
  opens the browser, since that's what the Desktop/Start Menu shortcut
  points at.
- Running the exe with arguments (``FileArchiver.exe scan --root ...``)
  behaves like ``python -m archiver ...`` for CLI usage from a terminal.
- A hidden ``--archiver-cli`` re-entry flag lets the bundled web UI spawn
  itself (via sys.executable) to run scan/analyze jobs in the background,
  mirroring what ``python -m archiver`` did in the unpackaged app.
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _base_dir() -> Path:
    """Directory containing bundled resources (tools, config template)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    """Writable per-user directory for config.yaml, artifacts/, archiver.db."""
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    data_dir = root / "FileArchiver"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _ensure_user_config(data_dir: Path, base_dir: Path) -> Path:
    config_path = data_dir / "config.yaml"
    if not config_path.exists():
        template = base_dir / "config.default.yaml"
        if template.exists():
            text = template.read_text(encoding="utf-8")
            text = text.replace("%USERPROFILE%", str(Path.home()))
            config_path.write_text(text, encoding="utf-8")
    return config_path


def _prepare_bundled_tools(base_dir: Path) -> None:
    """Put bundled Tesseract/FFmpeg/Poppler/Ghostscript/qpdf on PATH and
    point faster-whisper at the bundled model, if present."""
    tools_bin = base_dir / "tools" / "bin"
    gs_bin = base_dir / "tools" / "ghostscript" / "bin"
    for extra_bin in (tools_bin, gs_bin):
        if extra_bin.is_dir():
            os.environ["PATH"] = str(extra_bin) + os.pathsep + os.environ.get("PATH", "")

    tessdata = base_dir / "tools" / "tessdata"
    if tessdata.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)

    # The Whisper model is a separate, optionally post-install-downloaded
    # component (see fetch_whisper_model.ps1) to keep the main installer
    # under GitHub's 2 GB release-asset limit. If it's missing, fall back
    # to faster-whisper's normal name-based resolution (downloads from
    # Hugging Face on first use), exactly like the unpackaged app.
    whisper_model_dir = base_dir / "tools" / "whisper-medium"
    if (whisper_model_dir / "model.bin").is_file():
        os.environ["ARCHIVER_WHISPER_MODEL_DIR"] = str(whisper_model_dir)


def _run_web_ui(data_dir: Path, config_path: Path) -> None:
    import yaml
    from archiver.web.app import create_app

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    flask_app = create_app(cfg, config_path=config_path)

    port = 5000

    def open_browser() -> None:
        time.sleep(1.5)
        webbrowser.open(f"http://127.0.0.1:{port}")

    threading.Thread(target=open_browser, daemon=True).start()
    flask_app.run(host="127.0.0.1", port=port, debug=False)


def main() -> None:
    base_dir = _base_dir()
    _prepare_bundled_tools(base_dir)

    data_dir = _data_dir()
    config_path = _ensure_user_config(data_dir, base_dir)

    args = sys.argv[1:]

    # Internal re-entry used by archiver/web/scan_manager.py to run
    # scan/analyze as a background subprocess of this same executable. The
    # parent process (see _run_web_ui below) already starts us with our
    # working directory set to data_dir via subprocess cwd=, so the
    # default relative "config.yaml" lookup in archiver/cli.py resolves
    # correctly without chdir'ing again here.
    if args and args[0] == "--archiver-cli":
        sys.argv = [sys.argv[0]] + args[1:]
        from archiver.cli import app

        app()
        return

    # Direct CLI usage from a terminal: FileArchiver.exe scan --root ...
    # Deliberately does NOT chdir into data_dir, so relative paths (e.g.
    # --root some\relative\folder) resolve against the caller's actual
    # working directory, exactly like the unpackaged `python -m archiver`.
    if args:
        from archiver.cli import app

        app()
        return

    # Double-click default: start the web review UI and open the browser.
    # Chdir so the default "./config.yaml" / "./artifacts" resolution in
    # archiver/cli.py and archiver/web/app.py lands in our per-user data
    # directory instead of wherever Explorer happened to launch us from.
    os.chdir(data_dir)
    _run_web_ui(data_dir, config_path)


if __name__ == "__main__":
    main()
