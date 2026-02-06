# Local File Archiver

Lokale Python-CLI die Dateien rekursiv scannt und Text extrahiert.

## Unterstützte Dateitypen

| Typ   | Methode               |
|-------|-----------------------|
| `.md`  | Direkt lesen (UTF-8) |
| `.txt` | Direkt lesen (UTF-8) |
| `.pdf` | PyMuPDF              |
| `.docx`| python-docx          |

## Setup

```bash
pip install -r requirements.txt
```

## Verwendung

```bash
# Mit --root Parameter
python -m archiver scan --root ./meine_dateien

# Oder Root-Verzeichnis aus config.yaml lesen
python -m archiver scan

# Eigene Config verwenden
python -m archiver scan --config pfad/zu/config.yaml
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

artifacts_dir: ./artifacts
```

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
