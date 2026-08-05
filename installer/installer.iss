; Inno Setup script for File Archiver.
;
; Expects the PyInstaller onedir build to already exist at
; packaging\dist\FileArchiver\ (built via packaging\archiver.spec) before
; this script is compiled. See BUILD.md for the full sequence.
;
; Build with:  ISCC installer\installer.iss

#define MyAppName "File Archiver"
#define MyAppVersion GetEnv('ARCHIVER_VERSION')
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "File Archiver Project"
#define MyAppExeName "FileArchiver.exe"
#define SourceDist "..\packaging\dist\FileArchiver"

; GitHub "owner/repo" used to build the download URL for the separate
; whisper-medium-model.zip release asset (see fetch_whisper_model.ps1).
; The release workflow passes the real value via /DGitHubRepo=... ; when
; building locally, either pass the same /D flag or edit this default.
#define GitHubRepo GetEnv('ARCHIVER_REPO')
#if GitHubRepo == ""
  #define GitHubRepo "YOUR-GITHUB-USER/file-archiver"
#endif

[Setup]
AppId={{B4B6E6B0-6E3B-4B7B-9D3B-5C9A8E1B7B4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=FileArchiver-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Program Files requires admin, which also keeps the (large) OCR/whisper
; payload out of a per-user profile.
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Downloads the ~1.5 GB Whisper "medium" model as a separate step, since
; it ships as its own GitHub release asset (see comment near GitHubRepo
; above and packaging\fetch_whisper_model.ps1). Requires internet access
; at install time; on failure the app still works for everything except
; audio/video transcription, which then falls back to on-demand download.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\fetch_whisper_model.ps1"" -Repo ""{#GitHubRepo}"" -DestDir ""{app}\tools\whisper-medium"""; StatusMsg: "Lade Whisper-Sprachmodell herunter (~1,5 GB, kann einige Minuten dauern)..."; Flags: waituntilterminated runascurrentuser
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove artifacts/config that File Archiver itself creates alongside the
; install (relevant for older/portable-style layouts); the primary,
; per-user data directory (%LOCALAPPDATA%\FileArchiver) is intentionally
; left in place so scan results and the review database survive an
; uninstall/reinstall - see the confirmation dialog below.
Type: filesandordirs; Name: "{app}\artifacts"

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := MsgBox('File Archiver deinstallieren?' + #13#10 + #13#10 +
    'Ihre gescannten Daten, Einstellungen und die Datenbank unter' + #13#10 +
    '%LOCALAPPDATA%\FileArchiver bleiben erhalten und werden NICHT gelöscht.',
    mbConfirmation, MB_YESNO) = IDYES;
end;
