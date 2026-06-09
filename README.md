# Local File Archiver

Lokale Python-CLI die Dateien rekursiv scannt und Text extrahiert.

## Unterstützte Dateitypen

| Typ | Methode |
|-----|---------|
| `.md` `.txt` | Direkt lesen (UTF-8) |
| `.pdf` | PyMuPDF (Text-PDFs) / OCRmyPDF + Tesseract (Scans) |
| `.docx` | python-docx |
| `.mp3` `.m4a` `.wav` `.ogg` | faster-whisper Transkription (deutsch) |
| `.mp4` `.mkv` `.avi` `.mov` `.webm` | ffmpeg Audio-Extraktion + Whisper |
| `.jpg` `.jpeg` `.png` `.tiff` `.gif` `.webp` | pytesseract OCR (deutsch) |

## Setup

```bash
pip install -r requirements.txt
```

**System-Dependencies (Ubuntu/Debian):**
```bash
sudo apt install -y tesseract-ocr tesseract-ocr-deu ffmpeg poppler-utils
```

## Verwendung

```bash
# Mit --root Parameter
python -m archiver scan --root ./meine_dateien

# Oder Root-Verzeichnis aus config.yaml lesen
python -m archiver scan

# Eigene Config verwenden
python -m archiver scan --config pfad/zu/config.yaml

# Analyse mit IONOS LLM (llama-3.3-70b)
python -m archiver analyze --use-llm

# Web-Review-Interface
python -m archiver serve --port 5002
```

## Konfiguration (config.yaml)

```yaml
root_dir: ./meine_dateien

ignore_patterns:
  - node_modules
  - .git
  - __pycache__
  - .cache

supported_extensions:
  - .md
  - .txt
  - .pdf
  - .docx
  - .mp3
  - .m4a
  - .wav
  - .ogg
  - .mp4
  - .mkv
  - .avi
  - .mov
  - .webm
  - .jpg
  - .jpeg
  - .png
  - .tiff
  - .gif
  - .webp

artifacts_dir: ./artifacts
whisper_enabled: true
whisper_model: medium
whisper_language: de
llm_sorting: true
llm_sorting_model: openai/llama-3.3-70b
llm_base_url: https://openai.inference.de-txl.ionos.com/v1
```

## OCR (Optical Character Recognition)

### Text-PDFs vs. Scan-PDFs
- **Text-PDFs**: PyMuPDF extrahiert Text direkt (schnell)
- **Scan-PDFs**: OCRmyPDF erkennt automatisch fehlende Textebene → Tesseract OCR mit deutschem Sprachmodell
- **Bilder**: pytesseract mit Tesseract `lang=deu`

### Sprache
Standard: **Deutsch** (`tesseract-ocr-deu`). Für andere Sprachen entsprechendes Paket installieren.

## Audio/Video-Transkription

- **Audio**: Direkte Whisper-Transkription
- **Video**: ffmpeg extrahiert Audiospur → Whisper transkribiert
- **Modell**: `medium` (bessere Qualität als `base`, ~1.5 GB Download)
- **Sprache**: `de` (deutsch) als Standard

## Ausgabe

Nach dem Scan werden folgende Artefakte erzeugt:

```
artifacts/
├── text/          # Extrahierter Text pro Datei (<id>.txt)
├── meta/          # Metadaten pro Datei (<id>.json)
└── report.csv     # Gesamtreport
```

### Metadaten (JSON)

Jede `<id>.json` enthält:
- `path` – Absoluter Dateipfad
- `size_bytes` – Dateigröße
- `mtime` – Letzte Änderung (ISO 8601, UTC)
- `sha256` – SHA-256 Hash
- `status` – `OK` oder `ERROR`

### Report (CSV)

Spalten: `path`, `type`, `text_path`, `hash`, `status`

## Fehlerhandling

Schlägt die Extraktion einer Datei fehl, wird `status=ERROR` gesetzt und die nächste Datei verarbeitet. Der Fehler wird in der Metadaten-JSON unter `error` gespeichert.
