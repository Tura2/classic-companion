; Companion's installer (Inno Setup 6). build.bat runs it after PyInstaller:
;   ISCC /DAppVersion=1.4.0 installer\companion.iss  ->  dist\CompanionSetup.exe
; Per user, no admin prompt: everything goes in %LOCALAPPDATA%\Programs\Companion.
; The AppId never changes, so a newer setup updates in place and keeps data\.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{921BA8EE-8E0A-475D-A097-9DF25F80918E}
AppName=Companion
AppVersion={#AppVersion}
AppVerName=Companion {#AppVersion}
AppPublisher=Tura2
AppPublisherURL=https://tura2.github.io/classic-companion/
AppSupportURL=https://github.com/Tura2/classic-companion/issues
AppUpdatesURL=https://github.com/Tura2/classic-companion/releases
PrivilegesRequired=lowest
DefaultDirName={autopf}\Companion
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=CompanionSetup
SetupIconFile=..\web\logo.ico
UninstallDisplayIcon={app}\Companion.exe
UninstallDisplayName=Companion
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Companion holds this mutex while it runs: setup and uninstall ask to close it first
AppMutex=Tura2.Companion
CloseApplications=yes
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"

[CustomMessages]
en.LaunchCompanion=Start Companion
he.LaunchCompanion=הפעלת Companion
en.DeleteData=Also delete your Companion data?%n%nThat's your character, settings, grind history and the shop prices you've seen. Choose No to keep it, so a reinstall picks up where you left off.
he.DeleteData=למחוק גם את המידע שלכם ב-Companion?%n%nזה הדמות, ההגדרות, היסטוריית הגריינד ומחירי החנויות שראיתם. בחרו "לא" כדי לשמור אותו, וכך התקנה חוזרת תמשיך מאיפה שהפסקתם.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; an update replaces the program's own files whole, never mixing old and new
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Companion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Companion"; Filename: "{app}\Companion.exe"
Name: "{autodesktop}\Companion"; Filename: "{app}\Companion.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Companion.exe"; Description: "{cm:LaunchCompanion}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; made by Companion as it runs, safe to remove: downloaded data, logs, pictures, report zips
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\debug"
Type: filesandordirs; Name: "{app}\reports"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function WantsDataDeleted(): Boolean;
var
  i: Integer;
begin
  { a silent uninstall keeps the data unless /DELETEDATA is given }
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/DELETEDATA') = 0 then
    begin
      Result := True;
      exit;
    end;
  if UninstallSilent then
    Result := False
  else
    Result := MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{app}\data')) then
    if WantsDataDeleted() then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      RemoveDir(ExpandConstant('{app}'));
    end;
end;
