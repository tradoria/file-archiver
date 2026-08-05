"""Text extraction for MD, TXT, PDF, DOCX, Audio, Video, Images."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# File type sets
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif", ".webp"}

# Global whisper model cache
_whisper_model = None
_whisper_available = None


class WhisperNotAvailableError(Exception):
    """Raised when whisper/ffmpeg is not available."""
    pass


def extract_text(path: Path, whisper_config: dict | None = None) -> str:
    """Extract text content from a file. Raises on failure."""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return _read_plain(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix in IMAGE_EXT:
        return _read_image(path)
    if suffix in AUDIO_EXT | VIDEO_EXT:
        return _transcribe_media(path, whisper_config or {})
    raise ValueError(f"Unsupported file type: {suffix}")


def _read_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extract text from PDF. Uses PyMuPDF for text-PDFs, OCRmyPDF for scanned PDFs."""
    import fitz  # PyMuPDF

    # First try: extract text with PyMuPDF
    text_parts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            text_parts.append(page.get_text())

    combined_text = "\n".join(text_parts).strip()

    # If text is substantial (>50 chars), it's likely a text-PDF
    if len(combined_text) > 50:
        return combined_text

    # Fallback: OCR with OCRmyPDF / Tesseract
    return _ocr_pdf(path)


def _ocr_pdf(path: Path) -> str:
    """OCR a scanned PDF using OCRmyPDF or pytesseract fallback."""
    try:
        import ocrmypdf
        import fitz

        # OCRmyPDF: add text layer to temp PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out:
            tmp_path = Path(tmp_out.name)

        ocrmypdf.ocr(
            input_file=path,
            output_file=tmp_path,
            language=["deu"],
            force_ocr=True,
            progress_bar=False,
        )

        # Extract text from OCR'd PDF
        text_parts: list[str] = []
        with fitz.open(tmp_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())

        # Cleanup temp file
        tmp_path.unlink(missing_ok=True)
        return "\n".join(text_parts)
    except Exception:
        pass

    # Fallback: pdf2image + pytesseract
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(path, dpi=200)
        text_parts = []
        for img in images:
            text = pytesseract.image_to_string(img, lang="deu")
            text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as exc:
        raise RuntimeError(f"OCR failed for {path}: {exc}") from exc


def _read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _read_image(path: Path) -> str:
    """OCR an image using pytesseract with German language."""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang="deu")
        return text.strip()
    except Exception as exc:
        raise RuntimeError(f"OCR failed for image {path}: {exc}") from exc


def _check_whisper_available() -> bool:
    """Check if faster-whisper and ffmpeg are available."""
    global _whisper_available

    if _whisper_available is not None:
        return _whisper_available

    # Check ffmpeg
    if not shutil.which("ffmpeg"):
        _whisper_available = False
        return False

    # Check faster-whisper
    try:
        from faster_whisper import WhisperModel
        _whisper_available = True
    except ImportError:
        _whisper_available = False

    return _whisper_available


def _get_whisper_model(model_name: str = "base"):
    """Get or create whisper model (cached)."""
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    from faster_whisper import WhisperModel

    # Packaged builds bundle the model on disk and point us at it via this
    # env var, so we load it directly instead of resolving/downloading by
    # name from Hugging Face.
    bundled_dir = os.environ.get("ARCHIVER_WHISPER_MODEL_DIR")
    model_source = bundled_dir if bundled_dir else model_name

    # Use CPU with int8 for efficiency
    _whisper_model = WhisperModel(model_source, device="cpu", compute_type="int8")
    return _whisper_model


def _extract_audio_from_video(video_path: Path, output_path: Path) -> None:
    """Extract audio track from video using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")


def _transcribe_media(path: Path, config: dict) -> str:
    """Transcribe audio/video file to text using faster-whisper (German)."""
    if not config.get("whisper_enabled", True):
        raise WhisperNotAvailableError("Whisper disabled in config")

    if not _check_whisper_available():
        raise WhisperNotAvailableError("ffmpeg or faster-whisper not available")

    suffix = path.suffix.lower()
    model_name = config.get("whisper_model", "base")

    # Get audio file path
    audio_path = path
    temp_audio = None

    try:
        # Extract audio from video if needed
        if suffix in VIDEO_EXT:
            temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_audio.close()
            audio_path = Path(temp_audio.name)
            _extract_audio_from_video(path, audio_path)

        # Transcribe with German language
        model = _get_whisper_model(model_name)
        whisper_language = config.get("whisper_language", "de")
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            language=whisper_language,
        )

        # Collect text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        transcript = " ".join(text_parts)

        # Add metadata header
        duration_mins = info.duration / 60
        header = f"[Transkript: {path.name}]\n[Dauer: {duration_mins:.1f} min, Sprache: {info.language}]\n\n"

        return header + transcript

    finally:
        # Cleanup temp file
        if temp_audio:
            try:
                Path(temp_audio.name).unlink()
            except Exception:
                pass
