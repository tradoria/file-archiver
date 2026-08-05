# File Archiver

**Bringt Ordnung in deine Dateien.** File Archiver durchsucht einen Ordner
(z. B. deine Dokumente), liest den Inhalt jeder Datei – auch aus Scans,
Fotos, Sprachnachrichten und Videos – und schlägt dir vor, wo sie am besten
hingehört. Am Ende entscheidest du per Klick, was übernommen wird.

Du brauchst dafür keine Kommandozeile und kein Python: Für Windows gibt es
einen fertigen Installer, der eine ganz normale App daraus macht – Symbol
anklicken, es öffnet sich ein Fenster im Browser, fertig.

[![Windows-Installer](https://img.shields.io/badge/Windows-Installer-0078D6?logo=windows&logoColor=white)](../../releases/latest)
[![Portable ZIP](https://img.shields.io/badge/Windows-Portable%20ZIP-informational)](../../releases/latest)
[![Lizenz](https://img.shields.io/badge/Lizenz-siehe%20Repository-lightgrey)](#)

## Für wen ist das?

- Du hast einen Ordner voller Dokumente, Scans, Fotos, Sprachmemos und
  Videos, die nie richtig einsortiert wurden.
- Du willst wissen, was eigentlich *drin steht* – auch in einem
  eingescannten PDF oder einer Sprachnachricht – ohne jede Datei einzeln zu
  öffnen.
- Du möchtest am Ende selbst entscheiden, was wohin verschoben wird, statt
  einem Tool blind zu vertrauen.

## So sieht's aus

| Dashboard | Scan starten |
|---|---|
| ![Dashboard mit Datei-Übersicht und Sortiervorschlägen](docs/screenshots/dashboard.png) | ![Ordner auswählen und Scan starten](docs/screenshots/scan.png) |

*(Screenshots folgen – siehe [docs/screenshots/README.md](docs/screenshots/) zum Nachreichen eigener Bilder.)*

## So einfach geht's (Windows)

1. **Herunterladen:** Aktuellste Version von der [Releases-Seite](../../releases/latest) laden – entweder `FileArchiver-Setup-<version>.exe` (klassischer Installer) oder `FileArchiver-Portable-<version>.zip` (einfach entpacken, kein Setup nötig).
2. **Installieren/Entpacken:** Installer durchklicken (fragt optional nach einer Desktop-Verknüpfung), oder ZIP an einen beliebigen Ort entpacken.
3. **Starten:** Verknüpfung bzw. `FileArchiver.exe` doppelklicken – der Browser öffnet sich automatisch mit der Oberfläche.
4. **Ordner scannen:** Unter „Scan" den Ordnerpfad eintragen (z. B. `C:\Users\Du\Dokumente`) und loslegen. Ergebnisse landen im Dashboard, wo du sie prüfen und einsortieren lassen kannst.

Ausführliche Build-Anleitung für Entwickler: siehe [BUILD.md](BUILD.md).

## Was passiert mit meinen Dateien?

Alles läuft **lokal auf deinem Rechner** – nichts wird irgendwo
hochgeladen, außer du aktivierst optional die LLM-Sortierung mit eigenem
API-Zugang. Gescannte Inhalte, Sortiervorschläge und deine Entscheidungen
landen in einer lokalen Datenbank (`%LOCALAPPDATA%\FileArchiver` in der
Windows-App, sonst `artifacts/` im Projektordner). Original-Dateien werden
beim Scannen nur gelesen, nicht verändert – verschoben/kopiert wird erst,
wenn du das per `copy`-Befehl bzw. im Export ausdrücklich anstößt.

---

## Unterstützte Dateitypen

| Typ | Methode |
|-----|---------|
| `.md` `.txt` | Direkt lesen (UTF-8) |
| `.pdf` | PyMuPDF (Text-PDFs) / OCRmyPDF + Tesseract (Scans) |
| `.docx` | python-docx |
| `.mp3` `.m4a` `.wav` `.ogg` | faster-whisper Transkription (deutsch) |
| `.mp4` `.mkv` `.avi` `.mov` `.webm` | ffmpeg Audio-Extraktion + Whisper |
| `.jpg` `.jpeg` `.png` `.tiff` `.gif` `.webp` | pytesseract OCR (deutsch) |

## Setup (aus dem Quellcode, alle Plattformen)

```bash
pip install -r requirements.txt
```

**System-Dependencies (Ubuntu/Debian):**
```bash
sudo apt install -y tesseract-ocr tesseract-ocr-deu ffmpeg poppler-utils
```

Für Windows gibt es die fertige App (siehe oben) – die bringt Tesseract,
FFmpeg, Poppler, Ghostscript und optional das Whisper-Modell bereits mit,
ganz ohne diese Schritte.

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
