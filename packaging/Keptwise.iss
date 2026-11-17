; Inno Setup script: turns build\app\Keptwise (the PyInstaller build) into
; dist\Keptwise-Setup.exe, the only file in dist.
;
; Don't run this by hand: packaging\build.ps1 runs it and passes the version:
;   ISCC.exe /DAppVersion=0.1.0 packaging\Keptwise.iss
;
; - Installs for this Windows user only (no admin needed), always into
;   %LOCALAPPDATA%\Programs\Keptwise, so there is only ever one copy.
; - An update deletes the old program files first, so nothing from an older
;   version is left behind. The data in %APPDATA%\Keptwise is never touched.
; - Run with /RELAUNCH (the app's own "Update now" does), it opens Keptwise
;   again when a silent install is done.
; - Adds a Start Menu shortcut (and a desktop one if ticked).
; - The uninstaller asks whether to keep the saves, notes and settings in
;   %APPDATA%\Keptwise. A silent uninstall keeps them, unless it is
;   run with /DELETEDATA.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

; The data folder in %APPDATA% (also the name the API keys are saved under).
; Only the install tests change it, so they never touch real data:
; ISCC /DDataName=KeptwiseInstallTest ...
#ifndef DataName
  #define DataName "Keptwise"
#endif

#define AppName "Keptwise"
#define AppExe "Keptwise.exe"

[Setup]
; Never change AppId: Windows uses it to find the installed app for updates.
AppId={{6E0C5B7A-3F1D-4C47-9A2B-5D8E1F4A7C21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Keptwise
AppPublisherURL=https://github.com/vptr-dev/keptwise
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; Always the same folder: no "install for all users" copy in Program Files.
UsePreviousAppDir=yes
DisableDirPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Keptwise-Setup
SetupIconFile=..\desktop\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Close the app if it's open, so its files can be replaced or removed.
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The old version's program files go first, so an update leaves nothing outdated.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#AppExe}"

[Files]
Source: "..\build\app\Keptwise\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; After a one-click update (silent, with /RELAUNCH): open the new version.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WantsRelaunch

[UninstallDelete]
; Files the app may have written into its own folder (Python caches and the like).
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
const
  DataFolderName = '{#DataName}';

function WantsRelaunch(): Boolean;
begin
  Result := WizardSilent() and (Pos('/RELAUNCH', UpperCase(GetCmdTail())) > 0);
end;

function DataFolder(): String;
begin
  Result := ExpandConstant('{userappdata}\') + DataFolderName;
end;

function WantsDataDeleted(): Boolean;
begin
  if UninstallSilent() then
    // Silent uninstall: keep the data unless told otherwise.
    Result := Pos('/DELETEDATA', UpperCase(GetCmdTail())) > 0
  else
    Result := MsgBox(
      'Do you also want to delete your saves, notes, transcripts and settings?' + #13#10 + #13#10 +
      'They are in ' + DataFolder() + '.' + #13#10 + #13#10 +
      'Choose No to keep them, so they are still there if you install Keptwise again.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure DeleteSavedKeys();
var
  Providers: array of String;
  I, Code: Integer;
begin
  // API keys live in Windows Credential Manager, named like the keyring package does.
  Providers := ['anthropic', 'openai', 'gemini', 'openrouter', 'ollama', 'lmstudio'];
  Exec(ExpandConstant('{sys}\cmdkey.exe'), '/delete:' + DataFolderName, '', SW_HIDE, ewWaitUntilTerminated, Code);
  for I := 0 to GetArrayLength(Providers) - 1 do
    Exec(ExpandConstant('{sys}\cmdkey.exe'), '/delete:' + Providers[I] + '@' + DataFolderName, '', SW_HIDE,
      ewWaitUntilTerminated, Code);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if DirExists(DataFolder()) and WantsDataDeleted() then
    begin
      DelTree(DataFolder(), True, True, True);
      DeleteSavedKeys();
    end;
  end;
end;
