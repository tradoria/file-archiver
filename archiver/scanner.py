"""Recursive file scanner with ignore patterns."""

from pathlib import Path


DEFAULT_IGNORE = {"node_modules", ".git", "__pycache__", ".cache"}

# Document types
DOC_EXT = {".md", ".txt", ".pdf", ".docx"}

# Audio types
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"}

# Video types
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"}

# Image types (OCR)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif", ".webp"}

# All supported extensions
SUPPORTED_EXT = DOC_EXT | AUDIO_EXT | VIDEO_EXT | IMAGE_EXT


def scan(
    root: Path,
    extensions: set[str] | None = None,
    ignore: set[str] | None = None,
) -> list[Path]:
    """Recursively scan *root* and return files matching *extensions*."""
    extensions = extensions or SUPPORTED_EXT
    ignore = ignore or DEFAULT_IGNORE

    found: list[Path] = []
    for item in sorted(root.rglob("*")):
        # skip ignored directory trees
        if any(part in ignore for part in item.parts):
            continue
        if item.is_file() and item.suffix.lower() in extensions:
            found.append(item)
    return found
