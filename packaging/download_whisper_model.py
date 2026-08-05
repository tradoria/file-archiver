"""Download the faster-whisper 'medium' CTranslate2 model for offline bundling.

Fetches the model files directly (not via the HF cache layout) into
packaging/tools/whisper-medium, so faster_whisper.WhisperModel can load it
as a plain local directory at runtime with no network access.
"""

from pathlib import Path

from huggingface_hub import snapshot_download

DEST = Path(__file__).parent / "tools" / "whisper-medium"


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        repo_id="Systran/faster-whisper-medium",
        local_dir=str(DEST),
    )
    print(f"Modell heruntergeladen nach: {path}")


if __name__ == "__main__":
    main()
