# BUILD.md — Windows-Build (portable EXE + Installer)

Diese Anleitung beschreibt, wie aus dem Python-Projekt `file-archiver` eine
portable Windows-Anwendung und ein klassischer Installer entstehen.

## Überblick: Was wird gebaut

| Artefakt | Beschreibung | Ungefähre Größe |
|---|---|---|
| `release/FileArchiver-Portable-<version>.zip` | Portabler Ordner, entpacken & starten, kein Setup nötig | ~850 MB |
| `release/FileArchiver-Setup-<version>.exe` | Klassischer Windows-Installer (Inno Setup) mit Deinstallation, Verknüpfungen | ~700–800 MB |
| `release/whisper-medium-model.zip` | Separates Sprachmodell für Audio/Video-Transkription | ~1,5 GB |

Das Whisper-`medium`-Modell ist **absichtlich ein separates Release-Asset**
und nicht in den beiden EXE-Paketen enthalten: GitHub Releases erlauben
maximal 2 GB pro Datei, und Modell + restliche Tools zusammen würden dieses
Limit reißen. Sowohl der Installer als auch die portable Version laden es
bei Bedarf automatisch bzw. auf Wunsch nach (siehe unten,
`fetch_whisper_model.ps1`). Ohne das Modell funktioniert die App vollständig
für PDF/DOCX/Bilder/OCR — nur Audio/Video-Transkription lädt das Modell dann
stattdessen beim ersten Gebrauch direkt von Hugging Face nach (Standard-
verhalten von faster-whisper, sofern zu dem Zeitpunkt Internet verfügbar ist).

## Architektur der App (zum Verständnis der Build-Schritte)

`file-archiver` ist im Kern ein **Python-CLI-Tool** (Typer:
`python -m archiver scan|analyze|serve|copy`), kein natives GUI-Programm.
Der Befehl `serve` startet einen lokalen Flask-Webserver mit einer
browserbasierten Review-Oberfläche (Jinja2-Templates unter
`archiver/web/templates/`). Der Windows-Build macht daraus eine App, die
sich wie eine gewöhnliche Anwendung anfühlt:

- Ein Doppelklick auf `FileArchiver.exe` (bzw. die Desktop-/Startmenü-
  Verknüpfung) startet `serve` im Hintergrund und öffnet automatisch den
  Standardbrowser.
- Direkter Aufruf mit Argumenten (`FileArchiver.exe scan --root ...`)
  verhält sich wie das ursprüngliche `python -m archiver scan --root ...`.

Das übernimmt [`packaging/launcher.py`](packaging/launcher.py) — der
tatsächliche PyInstaller-Einstiegspunkt, ein dünner Wrapper um das
unveränderte `archiver`-Package.

## Externe Programme, die die App braucht

Diese sind **keine Python-Pakete** und werden als Binärdateien mitgeliefert
(siehe `packaging/tools/`):

| Tool | Wofür | Quelle |
|---|---|---|
| Tesseract OCR (+ deu/eng/osd) | Bild-OCR, Fallback für Scan-PDFs | UB-Mannheim-Installer, extrahiert |
| FFmpeg | Audiospur aus Videos extrahieren | gyan.dev "essentials"-Build |
| Poppler (pdftoppm/pdftocairo) | PDF→Bild-Konvertierung für `pdf2image` | poppler-windows (oschwartz10612) |
| Ghostscript | Backend von OCRmyPDF für Scan-PDFs | ghostpdl-downloads (Artifex) |
| qpdf | Wird von OCRmyPDF intern verwendet | qpdf-Projekt |
| faster-whisper "medium"-Modell | Audio/Video-Transkription (separates Asset) | Hugging Face `Systran/faster-whisper-medium` |

Alle Tools landen in `packaging/tools/` und werden von
[`packaging/launcher.py`](packaging/launcher.py) beim Start automatisch dem
`PATH` vorangestellt bzw. per Umgebungsvariable (`TESSDATA_PREFIX`,
`ARCHIVER_WHISPER_MODEL_DIR`) bekanntgemacht — der eigentliche Code in
`archiver/` weiß nichts davon und funktioniert unverändert auch außerhalb
der gebauten App (z. B. mit systemweit installiertem Tesseract/FFmpeg).

## Voraussetzungen zum Bauen

- Windows 10/11
- Python 3.12 (3.10+ sollte funktionieren)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`)
- 7-Zip (`winget install 7zip.7zip`) — wird nur von `download_tools.ps1`
  gebraucht, um die Tesseract-/Ghostscript-Installer (NSIS-Format) ohne
  Adminrechte zu entpacken
- Internetzugang (lädt insgesamt ca. 2,3 GB an Werkzeugen + Modell)
- Freier Speicherplatz: mind. 6 GB (Downloads + Build-Zwischendateien + Output)

## Build-Schritte

Alle Befehle aus dem Projekt-Root (`file-archiver-main/`) ausführen.

### 1. Python-Abhängigkeiten installieren

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

`pyinstaller` ist die einzige zusätzliche Abhängigkeit, die nur für den
Windows-Build gebraucht wird — alles andere (inkl. `ocrmypdf`,
`pytesseract`, `pdf2image`) steht bereits in `requirements.txt`.

### 2. App-Icon erzeugen

```powershell
python packaging/make_icon.py
```

Erzeugt `packaging/icon.ico`. Das Projekt selbst enthält kein Icon, es wird
hier aus einem einfachen Farbverlauf-Design generiert.

### 3. Externe Tools herunterladen

```powershell
pwsh packaging/download_tools.ps1
```

Füllt `packaging/tools/{bin,tessdata,ghostscript}` mit den oben genannten
Werkzeugen. Dauert je nach Verbindung einige Minuten (~400 MB Download).

**Hinweis zu Antivirus/EDR:** Auf Firmenrechnern mit strikten Microsoft-
Defender-ASR-Regeln (`Block executable files from running unless they meet
a prevalence, age, or trusted list criterion`) können frisch heruntergeladene,
unsignierte .exe-Dateien blockiert werden — nicht nur beim Ausführen,
sondern teils auch beim Lesen/Kopieren. Das ist keine Fehlfunktion dieses
Scripts, sondern eine von der IT gesetzte Richtlinie. Abhilfe: auf einem
weniger restriktiven Rechner bauen, oder die IT um eine Ausnahme für den
Build-Ordner bitten. `download_tools.ps1` verwendet bewusst den etablierten
gyan.dev-FFmpeg-Build statt der BtbN-CI-Nightlies, weil gut etablierte,
oft heruntergeladene Builds seltener von Reputations-Heuristiken geblockt
werden.

### 4. Whisper-Modell herunterladen

```powershell
python packaging/download_whisper_model.py
```

Lädt `Systran/faster-whisper-medium` (~1,5 GB) nach
`packaging/tools/whisper-medium/`. Wird **nicht** in den PyInstaller-Bundle
eingebettet (siehe oben), sondern separat als `whisper-medium-model.zip`
verpackt (Schritt 7).

### 5. PyInstaller-Build

```powershell
python -m PyInstaller packaging/archiver.spec --noconfirm --distpath packaging/dist --workpath packaging/build
```

Ergebnis: `packaging/dist/FileArchiver/` (onedir-Build, kein `--onefile`).

**Warum onedir statt onefile:** Mit ~900 MB an eingebetteten Werkzeugen
würde ein `--onefile`-Build bei **jedem** Start alles neu in einen Temp-
Ordner entpacken — spürbar langsamer Programmstart und unnötiger
Plattenverschleiß. Der onedir-Ordner ist trotzdem "portabel" im
gewünschten Sinn: zippen, verschicken, entpacken, `FileArchiver.exe`
doppelklicken — fertig, keine Installation nötig.

Die App bleibt bewusst eine **Konsolen-App** (`console=True` in
`archiver.spec`): Ohne Konsole würden alle `typer.echo()`-Ausgaben und
Fehlermeldungen der CLI-Befehle (`scan`, `analyze`, …) und auch die
Startmeldungen des Webservers verschluckt. Beim Doppelklick öffnet sich
daher ein Konsolenfenster neben dem Browser-Tab — bewusster Kompromiss
zwischen "fühlt sich wie eine App an" und "Fehler sind sichtbar".

### 6. Smoke-Test

```powershell
packaging\dist\FileArchiver\FileArchiver.exe --help
```

Sollte die Typer-Befehlsübersicht zeigen. Test eines echten Scans:

```powershell
packaging\dist\FileArchiver\FileArchiver.exe scan --root "C:\Pfad\zu\Testdateien"
```

### 7. Portable ZIP + Whisper-Modell-Asset packen

```powershell
Compress-Archive -Path "packaging\dist\FileArchiver\*" -DestinationPath "release\FileArchiver-Portable-<version>.zip"
Compress-Archive -Path "packaging\tools\whisper-medium\*" -DestinationPath "release\whisper-medium-model.zip"
```

### 8. Installer bauen

```powershell
$env:ARCHIVER_VERSION = "1.0.0"
$env:ARCHIVER_REPO = "<github-user>/<repo>"   # für den automatischen Modell-Download im Installer
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\installer.iss
```

Ergebnis: `release\FileArchiver-Setup-1.0.0.exe`.

`ARCHIVER_REPO` muss auf das echte GitHub-Repository zeigen (`owner/repo`),
weil der Installer daraus die Download-URL für
`whisper-medium-model.zip` baut (`.../releases/latest/download/...`, siehe
[`installer/installer.iss`](installer/installer.iss) und
[`packaging/fetch_whisper_model.ps1`](packaging/fetch_whisper_model.ps1)).
Ohne gesetzten Wert wird der Platzhalter `YOUR-GITHUB-USER/file-archiver`
verwendet — vor einem echten Release unbedingt anpassen (die GitHub Action,
siehe unten, setzt das automatisch).

## Automatischer Release-Build (GitHub Actions)

[`.github/workflows/release.yml`](.github/workflows/release.yml) führt
alle obigen Schritte automatisch aus, sobald ein Tag wie `v1.0.0` gepusht
wird, und hängt die drei Artefakte (Portable-ZIP, Setup-EXE,
Whisper-Modell-ZIP) an das zugehörige GitHub Release an:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Deinstallation

Der Installer registriert einen normalen Windows-Uninstaller
(Einstellungen → Apps, oder `{app}\unins000.exe`). Er fragt vor dem
Entfernen nach, ob die persönlichen Daten unter
`%LOCALAPPDATA%\FileArchiver` (Konfiguration, gescannte Artefakte,
Review-Datenbank) erhalten bleiben sollen — standardmäßig **ja**, damit ein
Update/Neuinstall keine Scan-Ergebnisse verliert. Wer wirklich alles
entfernen will, löscht diesen Ordner danach manuell.

## Desktop-/Startmenü-Verknüpfung

Der Installer legt automatisch einen Startmenü-Eintrag an; die
Desktop-Verknüpfung ist optional (Checkbox während der Installation,
standardmäßig **nicht** angehakt). Beide starten `FileArchiver.exe` ohne
Argumente — also die Web-UI mit automatisch geöffnetem Browser.

## Wo persönliche Daten liegen

Da die App i. d. R. nach `C:\Program Files\File Archiver` installiert wird
(kein Schreibzugriff für normale Nutzer), legt
[`packaging/launcher.py`](packaging/launcher.py) Konfiguration und
Scan-Ergebnisse stattdessen unter `%LOCALAPPDATA%\FileArchiver` an:

```
%LOCALAPPDATA%\FileArchiver\
├── config.yaml       (aus packaging/config.default.yaml kopiert, beim ersten Start)
└── artifacts\
    ├── text\
    ├── meta\
    ├── report.csv
    └── archiver.db
```

## Vorgenommene Code-Änderungen (gegenüber dem Original-Projekt)

Die eigentliche Scan-/Extraktions-/Sortierlogik in `archiver/` wurde
**nicht verändert**. Folgende Anpassungen waren nötig, damit die gebaute
Version funktioniert bzw. sicher ist — alle sind minimal und wirken sich
auf die unveränderte Nutzung per `python -m archiver` nicht negativ aus:

1. **[`archiver/web/scan_manager.py`](archiver/web/scan_manager.py)** —
   Die Web-UI startete Scan/Analyse bisher über
   `subprocess.Popen(["python", "-m", "archiver", ...])`. In einer
   gefrorenen EXE gibt es kein passendes `python` im PATH. Umgestellt auf
   `sys.executable` mit einem internen `--archiver-cli`-Reentry-Flag
   (siehe `packaging/launcher.py`), das für den unveränderten
   `python -m archiver`-Fall identisch funktioniert.

2. **[`archiver/cli.py`](archiver/cli.py)**, `serve`-Befehl — lief bisher
   mit `host="0.0.0.0", debug=True`. `debug=True` aktiviert Flasks
   Reloader, der sich selbst per `sys.executable` + `sys.argv` neu startet
   — in einer gefrorenen EXE führt das zu einem rekursiven
   Neustart-Loop der ganzen Anwendung. `0.0.0.0` mit aktivem
   Werkzeug-Debugger ist zudem ein bekanntes Sicherheitsrisiko (der
   interaktive Debugger erlaubt beliebigen Code auszuführen, wenn er von
   außen erreichbar ist). Geändert auf `host="127.0.0.1", debug=False` —
   sowohl notwendig für den gebauten Build als auch eine echte
   Sicherheitskorrektur.

3. **[`archiver/web/app.py`](archiver/web/app.py)** — `create_app()` rief
   `init_db()` auf, bevor das `artifacts`-Verzeichnis existierte. Das
   funktionierte in der Original-App nur "zufällig", weil man praktisch
   immer zuerst `scan` ausführt (was den Ordner anlegt) und danach erst
   `serve`. In der gebauten App ist der erste Aufruf oft `serve` (Web-UI
   per Doppelklick) ohne vorherigen Scan — das führte zu einem Absturz
   beim allerersten Start. Fix: `artifacts_dir.mkdir(parents=True,
   exist_ok=True)` vor der DB-Initialisierung.

4. **[`archiver/extractor.py`](archiver/extractor.py)** — `faster-whisper`
   lädt Modelle standardmäßig per Name (löst automatisch herunter/aus dem
   HF-Cache auf). Ergänzt um einen Fallback auf die Umgebungsvariable
   `ARCHIVER_WHISPER_MODEL_DIR`: ist sie gesetzt (vom Launcher, wenn ein
   lokal mitgeliefertes Modell existiert), wird das Modell direkt von dort
   geladen statt namensbasiert aufgelöst — ohne diese Variable ist das
   Verhalten exakt wie zuvor.

5. **[`archiver/web/templates/base.html`](archiver/web/templates/base.html)**
   — lud Tailwind CSS bisher von `cdn.tailwindcss.com`. Für eine wirklich
   offline-fähige, portable App wurde das Skript einmalig heruntergeladen
   und liegt jetzt lokal unter `archiver/web/static/tailwindcss.js`;
   referenziert über Flasks `url_for('static', ...)`. Identisches
   Rendering, keine Internetabhängigkeit mehr für die UI selbst.

Keine dieser Änderungen verändert, wie Dateien gescannt, extrahiert,
OCR-erkannt, transkribiert oder sortiert werden.

## Bekannte Einschränkungen

- **Unsigniert:** Weder `FileArchiver.exe` noch die mitgelieferten
  Drittanbieter-Tools sind code-signiert. Windows SmartScreen zeigt beim
  ersten Start ggf. eine Warnung ("Windows hat den Start dieser App
  geschützt"); auf Firmenrechnern mit strikten Defender-ASR-Regeln kann die
  Ausführung sogar ganz blockiert werden (siehe Hinweis in Schritt 3). Für
  eine breitere Verteilung empfiehlt sich ein Code-Signing-Zertifikat.
- **Whisper-Modell-Download beim Setup** setzt Internetzugang zum
  Installationszeitpunkt voraus (für die volle Transkriptionsqualität mit
  `medium`). Schlägt der Download fehl, funktioniert die App weiterhin für
  alle anderen Dateitypen; Audio/Video transkribiert dann erst nach
  manuellem erneuten Ausführen von `fetch_whisper_model.ps1` oder beim
  ersten Gebrauch über einen Live-Download von Hugging Face.
- **IONOS-LLM-Sortierung** (`--use-llm`) benötigt einen API-Token in der
  Umgebungsvariable `IONOS_AI_TOKEN` — in der mitgelieferten
  Standard-Konfiguration deaktiviert (`llm_sorting: false`), da kein Token
  mitgeliefert wird/werden kann.
