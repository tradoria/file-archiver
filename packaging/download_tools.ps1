<#
.SYNOPSIS
    Downloads and assembles the external tools bundled into the Windows
    build: Tesseract OCR (+ German/English/OSD data), FFmpeg, Poppler,
    Ghostscript and qpdf.

.DESCRIPTION
    Populates packaging\tools\ with everything archiver.spec expects to
    find there. Run once before building with PyInstaller. Requires
    7-Zip (7z.exe) to unpack the Tesseract/Ghostscript installers, which
    are NSIS self-extractors rather than plain zip files - 7-Zip ships
    preinstalled on GitHub's windows-latest runners, and is commonly
    already present on developer machines; installs it via winget if
    missing.

    Safe to re-run: downloads go to a scratch folder (packaging\_downloads)
    that can be deleted afterwards, and packaging\tools\ is rebuilt from
    scratch each time.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
$Packaging = $PSScriptRoot
$Downloads = Join-Path $Packaging "_downloads"
$Tools = Join-Path $Packaging "tools"

New-Item -ItemType Directory -Force -Path $Downloads | Out-Null
New-Item -ItemType Directory -Force -Path "$Tools\bin" | Out-Null
New-Item -ItemType Directory -Force -Path "$Tools\tessdata" | Out-Null

# --- Locate 7-Zip (needed to unpack the NSIS-based installers) ---------
$7z = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
if (-not $7z) { $7z = "C:\Program Files\7-Zip\7z.exe" }
if (-not (Test-Path $7z)) {
    Write-Host "7-Zip nicht gefunden, installiere via winget..."
    winget install --id 7zip.7zip -e --silent --accept-package-agreements --accept-source-agreements
    $7z = "C:\Program Files\7-Zip\7z.exe"
}

# --- qpdf ---------------------------------------------------------------
Write-Host "Lade qpdf..."
$qpdfAsset = (Invoke-RestMethod "https://api.github.com/repos/qpdf/qpdf/releases/latest").assets |
    Where-Object { $_.name -like "*mingw64.zip" } | Select-Object -First 1
Invoke-WebRequest $qpdfAsset.browser_download_url -OutFile "$Downloads\qpdf.zip"
Expand-Archive -Path "$Downloads\qpdf.zip" -DestinationPath "$Downloads\qpdf_extract" -Force
$qpdfBin = Get-ChildItem "$Downloads\qpdf_extract" -Recurse -Directory -Filter "bin" | Select-Object -First 1 -ExpandProperty FullName
Copy-Item "$qpdfBin\*.exe" "$Tools\bin\" -Force
Copy-Item "$qpdfBin\*.dll" "$Tools\bin\" -Force

# --- Poppler (pdftoppm/pdftocairo, used by pdf2image) --------------------
Write-Host "Lade Poppler..."
$popplerAsset = (Invoke-RestMethod "https://api.github.com/repos/oschwartz10612/poppler-windows/releases/latest").assets |
    Select-Object -First 1
Invoke-WebRequest $popplerAsset.browser_download_url -OutFile "$Downloads\poppler.zip"
Expand-Archive -Path "$Downloads\poppler.zip" -DestinationPath "$Downloads\poppler_extract" -Force
$popplerBin = Get-ChildItem "$Downloads\poppler_extract" -Recurse -Directory -Filter "bin" | Select-Object -First 1 -ExpandProperty FullName
Copy-Item "$popplerBin\*.exe" "$Tools\bin\" -Force
Copy-Item "$popplerBin\*.dll" "$Tools\bin\" -Force

# --- FFmpeg (audio extraction from video) ---------------------------------
# Deliberately using the gyan.dev "essentials" build (a well-known, widely
# downloaded, stable release) rather than BtbN's per-commit CI nightlies:
# the nightlies churn a new file hash on every build with zero reputation
# history, which is exactly the kind of file some endpoint-security
# products (Defender ASR "block unless prevalence/age/trusted" and
# similar EDR rules) flag and block on managed/corporate machines.
Write-Host "Lade FFmpeg (gyan.dev essentials build)..."
Invoke-WebRequest "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile "$Downloads\ffmpeg.zip"
Expand-Archive -Path "$Downloads\ffmpeg.zip" -DestinationPath "$Downloads\ffmpeg_extract" -Force
$ffmpegBin = Get-ChildItem "$Downloads\ffmpeg_extract" -Recurse -Directory -Filter "bin" | Select-Object -First 1 -ExpandProperty FullName
Copy-Item "$ffmpegBin\ffmpeg.exe" "$Tools\bin\" -Force

# --- Tesseract OCR (NSIS installer, extracted without running/admin) -----
Write-Host "Lade Tesseract..."
$tessPage = Invoke-WebRequest "https://digi.bib.uni-mannheim.de/tesseract/" -UseBasicParsing
$tessName = ($tessPage.Links | Where-Object { $_.href -like "*tesseract-ocr-w64-setup-5*" } |
    Select-Object -ExpandProperty href | Sort-Object | Select-Object -Last 1)
Invoke-WebRequest "https://digi.bib.uni-mannheim.de/tesseract/$tessName" -OutFile "$Downloads\tesseract-installer.exe"
New-Item -ItemType Directory -Force -Path "$Downloads\tesseract_install" | Out-Null
& $7z x "$Downloads\tesseract-installer.exe" "-o$Downloads\tesseract_install" -y | Out-Null
Copy-Item "$Downloads\tesseract_install\tesseract.exe" "$Tools\bin\" -Force
Copy-Item "$Downloads\tesseract_install\*.dll" "$Tools\bin\" -Force

Write-Host "Lade tessdata (deu/eng/osd, best quality)..."
Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/deu.traineddata" -OutFile "$Tools\tessdata\deu.traineddata"
Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata" -OutFile "$Tools\tessdata\eng.traineddata"
Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/osd.traineddata" -OutFile "$Tools\tessdata\osd.traineddata"

# --- Ghostscript (NSIS installer; OCRmyPDF's scanned-PDF backend) --------
Write-Host "Lade Ghostscript..."
$gsAsset = (Invoke-RestMethod "https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest").assets |
    Where-Object { $_.name -like "gs*w64.exe" } | Select-Object -First 1
Invoke-WebRequest $gsAsset.browser_download_url -OutFile "$Downloads\gs-installer.exe"
New-Item -ItemType Directory -Force -Path "$Downloads\gs_install" | Out-Null
& $7z x "$Downloads\gs-installer.exe" "-o$Downloads\gs_install" -y | Out-Null

New-Item -ItemType Directory -Force -Path "$Tools\ghostscript" | Out-Null
Copy-Item "$Downloads\gs_install\bin" "$Tools\ghostscript\bin" -Recurse -Force
Copy-Item "$Downloads\gs_install\lib" "$Tools\ghostscript\lib" -Recurse -Force
Copy-Item "$Downloads\gs_install\Resource" "$Tools\ghostscript\Resource" -Recurse -Force
Copy-Item "$Downloads\gs_install\iccprofiles" "$Tools\ghostscript\iccprofiles" -Recurse -Force

Write-Host ""
Write-Host "Fertig. packaging\tools Gesamtgroesse:"
"{0:N1} MB" -f ((Get-ChildItem $Tools -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
