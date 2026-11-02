; Copyright (c) 2026 Ivan Soprun
; Agent SI installer (Inno Setup 6).
;
; Payload: the exe-build stage folder (dist/stage) produced by
; packaging/build_app.ps1 — the frozen sidecar exe at the folder
; root (stage/AgentSI.exe, one-file or the one-dir folder), the web
; tree, the lane data dirs, LICENSE and
; docs/third_party_notices/NOTICES.md with the per-component licence
; texts. packaging/installer/build.py scans that folder clean (no
; projects, runs, keys, test data) before compiling this script, so
; a fresh install starts clean: nothing from the build machine rides
; in the payload.
;
; Shortcuts (owner 2026-11-02): Start-menu entry + desktop shortcut,
; BOTH checked by default in the wizard, both named 'Agent SI' with
; the SI icon (the exe carries icon.ico), opening AgentSI.exe in its
; folder with the working directory set to it. Uninstall removes
; both; the data folder stays unless the user opts into deleting it.
;
; Compile from the checkout root with ISCC.exe on PATH:
;   ISCC.exe /Odist "/F AgentSI-setup-{#AppVersion}" /DAppVersion=0.1.0 packaging/installer/agent_si.iss
; Compiling this file directly in the Inno IDE also works: the
; defaults below match the frozen portable contract (exe
; AgentSI.exe, version 0.1.0).
;
; The installed app is windowed (no console, no terminal): the
; frozen sidecar is built console-free and the Run entry below starts it
; with nowait, never through cmd.

#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

[Setup]
AppId=com.agentsi.app
AppName=Agent SI
AppVerName=Agent SI {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=Ivan Soprun
AppCopyright=Copyright (c) 2026 Ivan Soprun
DefaultDirName={localappdata}\Programs\Agent SI
DefaultGroupName=Agent SI
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=AgentSI-setup-{#AppVersion}
LicenseFile=..\..\LICENSE
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\AgentSI.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[CustomMessages]
en.LaunchAgentSI=Launch Agent SI
uk.LaunchAgentSI=Запустити Agent SI
en.DeleteDataPrompt=Also delete your Agent SI data folder (projects, tasks, settings and runs)? By default it is kept.
uk.DeleteDataPrompt=Також видалити папку даних Agent SI (проєкти, завдання, налаштування та запуски)? Типово вона зберігається.

[Tasks]
; No Flags: unchecked — the desktop shortcut installs by default
; (owner 2026-11-02: both shortcuts checked by default in the wizard).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The entry above installs the whole stage tree: AgentSI.exe,
; web/, migrations/, locale/, kb-data/, watcher/, LICENSE and
; docs/third_party_notices/NOTICES.md (licence + third-party notices).

[Icons]
Name: "{group}\Agent SI"; Filename: "{app}\AgentSI.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,Agent SI}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Agent SI"; Filename: "{app}\AgentSI.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AgentSI.exe"; Description: "{cm:LaunchAgentSI}"; Flags: nowait postinstall skipifsilent

; Uninstall removes the app tree but leaves the user's data folder
; ({app}\data from a writable install, %LOCALAPPDATA%\AgentSI\data
; from the read-only fallback) unless the user opts into deleting
; it in the uninstall prompt below.
[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"; Check: ShouldDeleteData
Type: filesandordirs; Name: "{localappdata}\AgentSI\data"; Check: ShouldDeleteData

[Code]
var
  DeleteData: Boolean;

function ShouldDeleteData(): Boolean;
begin
  Result := DeleteData;
end;

function InitializeUninstall(): Boolean;
var
  Answer: Integer;
begin
  Result := True;
  DeleteData := False;
  if UninstallSilent() then
    Exit;
  Answer := MsgBox(CustomMessage('DeleteDataPrompt'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
  DeleteData := (Answer = IDYES);
end;
