<#
.SYNOPSIS
    Downloads the faster-whisper "medium" model and places it next to this
    script under tools\whisper-medium, so File Archiver can transcribe
    audio/video fully offline.

.DESCRIPTION
    The model (~1.5 GB) ships as a separate GitHub release asset
    (whisper-medium-model.zip) rather than being baked into the main
    installer/portable build, to stay under GitHub's 2 GB per-file release
    asset limit. The Windows installer runs this automatically; portable
    users can double-click it (or run it from PowerShell) once, any time.

    Without this model, File Archiver still works for all other file
    types (PDF/DOCX/images/OCR) - audio/video transcription will instead
    fall back to downloading the model from Hugging Face on first use,
    same as the unpackaged app, provided there is internet access then.
#>
param(
    [string]$Repo = "YOUR-GITHUB-USER/file-archiver",
    [string]$DestDir = "$PSScriptRoot\tools\whisper-medium"
)

$ErrorActionPreference = "Stop"
$url = "https://github.com/$Repo/releases/latest/download/whisper-medium-model.zip"
$zipPath = Join-Path $env:TEMP "whisper-medium-model.zip"

Write-Host "Lade Whisper 'medium'-Sprachmodell (~1,5 GB) von:"
Write-Host "  $url"
Write-Host "Das kann je nach Verbindung einige Minuten dauern..."

try {
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $DestDir -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    Write-Host "Fertig. Modell liegt unter: $DestDir"
} catch {
    Write-Warning "Download des Whisper-Modells fehlgeschlagen: $_"
    Write-Warning "Audio/Video-Transkription laedt das Modell dann beim ersten Gebrauch stattdessen automatisch aus dem Internet nach (Standardverhalten von faster-whisper). Sie koennen dieses Skript jederzeit erneut ausfuehren, um es erneut zu versuchen."
}
