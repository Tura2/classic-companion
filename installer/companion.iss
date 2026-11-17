; Companion's installer (Inno Setup 6). build.bat runs it after PyInstaller:
;   ISCC /DAppVersion=1.4.0 installer\companion.iss  ->  dist\CompanionSetup.exe
; Per user, no admin prompt: everything goes in %LOCALAPPDATA%\Programs\Companion.
; The AppId never changes, so a newer setup updates in place and keeps data\.

#if Ver < EncodeVer(6,7,0)
  #error The installer's look (WizardBackColor, dark style) needs Inno Setup 6.7 or newer: winget upgrade JRSoftware.InnoSetup
#endif

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; What gets installed: the PyInstaller folder. /DSourceDir=... points elsewhere (a stub, to try the look).
#ifndef SourceDir
  #define SourceDir "..\dist\Companion"
#endif
; a test build must never replace (and on uninstall, delete) the real shortcuts
#ifdef TestBuild
  #define IconName "Companion (test)"
#else
  #define IconName "Companion"
#endif

[Setup]
#ifdef TestBuild
; /DTestBuild: a look-only build with its own AppId, so trying it never touches a real install
AppId={{5B0C3E3A-7D4E-4F55-9C1B-2F7A0D8E6C11}
AppName=Companion (test)
Compression=none
#else
AppId={{921BA8EE-8E0A-475D-A097-9DF25F80918E}
AppName=Companion
Compression=lzma2/max
#endif
AppVersion={#AppVersion}
AppVerName=Companion {#AppVersion}
AppPublisher=Tura2
AppPublisherURL=https://tura2.github.io/classic-companion/
AppSupportURL=https://github.com/Tura2/classic-companion/issues
AppUpdatesURL=https://github.com/Tura2/classic-companion/releases
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#IconName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
; three pages: Welcome (with the desktop shortcut box) -> Installing -> Finish
DisableWelcomePage=no
OutputDir=..\dist
OutputBaseFilename=CompanionSetup
SetupIconFile=..\web\logo.ico
UninstallDisplayIcon={app}\Companion.exe
UninstallDisplayName=Companion
SolidCompression=yes
; Companion's dark HUD look: forced dark, the HUD's blue, the logo panel (tools/make_installer_art.py)
WizardStyle=modern dark hidebevels
WizardBackColor=#252E3F
WizardImageFile=art\side-202x386.png,art\side-269x515.png,art\side-336x643.png,art\side-430x824.png
WizardSmallImageFile=..\web\logo.png
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Companion holds the mutex Tura2.Companion while it runs. Setup and uninstall check it in [Code]
; (not AppMutex): an update started by Companion itself waits for it to close instead of failing.
CloseApplications=yes
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Messages]
en.WelcomeLabel1=Welcome to Companion
he.WelcomeLabel1=ברוכים הבאים ל-Companion
en.WelcomeLabel2=Companion reads your MapleStory Classic screen and tells you where to grind, what to sell and which quests are worth it.%n%nSetup takes about a minute. Your game files are not changed.
he.WelcomeLabel2=Companion קורא את המסך של MapleStory Classic ואומר לכם איפה לעשות גריינד, מה למכור ואילו קווסטים שווים את זה.%n%nההתקנה לוקחת בערך דקה. קבצי המשחק שלכם לא משתנים.
en.WizardInstalling=Installing Companion
he.WizardInstalling=מתקינים את Companion
en.InstallingLabel=This takes about a minute.
he.InstallingLabel=זה לוקח בערך דקה.
en.FinishedHeadingLabel=Companion is ready
he.FinishedHeadingLabel=Companion מוכן
en.FinishedLabel=Open MapleStory Classic, then start Companion. It finds the game window by itself.
he.FinishedLabel=פתחו את MapleStory Classic ואז הפעילו את Companion. הוא ימצא את חלון המשחק לבד.
en.FinishedLabelNoIcons=Open MapleStory Classic, then start Companion. It finds the game window by itself.
he.FinishedLabelNoIcons=פתחו את MapleStory Classic ואז הפעילו את Companion. הוא ימצא את חלון המשחק לבד.

[CustomMessages]
he.CreateDesktopIcon=יצירת קיצור דרך בשולחן ה&עבודה
en.LaunchCompanion=Start Companion
he.LaunchCompanion=הפעלת Companion
en.DeleteData=Also delete your Companion data?%n%nThat's your character, settings, grind history and the shop prices you've seen. Choose No to keep it, so a reinstall picks up where you left off.
he.DeleteData=למחוק גם את המידע שלכם ב-Companion?%n%nזה הדמות, ההגדרות, היסטוריית הגריינד ומחירי החנויות שראיתם. בחרו "לא" כדי לשמור אותו, וכך התקנה חוזרת תמשיך מאיפה שהפסקתם.
en.CloseCompanion=Companion is open. Close its window, then click Retry.
he.CloseCompanion=Companion פתוח. סגרו את החלון שלו ולחצו "נסה שוב".

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; an update replaces the program's own files whole, never mixing old and new
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; the setup's own look, unpacked to {tmp} while it runs; never installed
Source: "art\DotGothic16-Latin.ttf"; Flags: dontcopy
Source: "art\side-*.png"; Flags: dontcopy
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#IconName}"; Filename: "{app}\Companion.exe"
Name: "{autodesktop}\{#IconName}"; Filename: "{app}\Companion.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Companion.exe"; Description: "{cm:LaunchCompanion}"; Flags: nowait postinstall skipifsilent
; an update Companion started (/UPDATE) starts the new version by itself
Filename: "{app}\Companion.exe"; Flags: nowait; Check: IsUpdate

[UninstallDelete]
; made by Companion as it runs, safe to remove: downloaded data, logs, pictures, report zips
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\debug"
Type: filesandordirs; Name: "{app}\reports"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function HasParam(Name: String): Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), Name) = 0 then
    begin
      Result := True;
      exit;
    end;
end;

function IsUpdate(): Boolean;
begin
  Result := HasParam('/UPDATE');
end;

function CompanionRunning(): Boolean;
begin
#ifdef TestBuild
  Result := False;
#else
  Result := CheckForMutexes('Tura2.Companion');
#endif
end;

{ Companion must be closed before its files are replaced or removed. An update Companion started
  itself gets up to 30 s for Companion to close; otherwise the player is asked to close it. }
function CompanionClosed(Silent: Boolean): Boolean;
var
  i: Integer;
begin
  Result := True;
  if IsUpdate() then
    for i := 1 to 60 do
    begin
      if not CompanionRunning() then
        exit;
      Sleep(500);
    end;
  while CompanionRunning() do
    if Silent or (MsgBox(CustomMessage('CloseCompanion'), mbError, MB_RETRYCANCEL) = IDCANCEL) then
    begin
      Result := False;
      exit;
    end;
end;

function InitializeSetup(): Boolean;
begin
  Result := CompanionClosed(WizardSilent);
end;

{ ---- The look: Companion's dark HUD, the logo panel on every page, the pixel font, an EXP bar ---- }

const
  FR_PRIVATE = $10;
  PIXEL_FONT = 'DotGothic16';
  AMBER = $0041A5F2;        { #F2A541, BGR }
  AMBER_LIGHT = $007AE0FF;  { #FFE07A }
  MUTED = $00D0BFB4;        { #B4BFD0 }
  TRACK = $0020150F;        { #0F1520 }
  TRACK_EDGE = $00170F0A;   { #0A0F17 }

var
  DesktopCheck: TNewCheckBox;
  InnerSide: TBitmapImage;
  ExpBar: TBitmapImage;
  ExpStep: Integer;

function AddFontResourceEx(FileName: String; Flags: Cardinal; Reserved: Cardinal): Integer;
  external 'AddFontResourceExW@gdi32.dll stdcall';

{ DotGothic16 has Latin letters only: Hebrew keeps Windows' own font. }
function UsePixelFont(): Boolean;
begin
  Result := ActiveLanguage <> 'he';
end;

procedure StyleHeading(Lbl: TNewStaticText);
begin
  Lbl.StyleElements := [seClient, seBorder];   { let our colour win over the dark style's }
  Lbl.Font.Color := AMBER;
  if UsePixelFont() then
  begin
    Lbl.Font.Name := PIXEL_FONT;
    Lbl.Font.Size := 17;
    Lbl.Font.Style := [];
  end else
  begin
    Lbl.Font.Size := 15;
    Lbl.Font.Style := [fsBold];
  end;
end;

procedure StyleBody(Lbl: TNewStaticText);
begin
  Lbl.StyleElements := [seClient, seBorder];
  Lbl.Font.Color := MUTED;
end;

procedure StyleButton(Btn: TNewButton);
begin
  if UsePixelFont() then
  begin
    Btn.Font.Name := PIXEL_FONT;
    Btn.Font.Size := 10;
  end;
end;

{ The side picture Inno picked for this screen's scaling isn't readable from script, so the
  inner pages load the same files themselves: the smallest one at least as wide as the panel. }
function SideArtFor(Width: Integer): String;
begin
  if Width <= 202 then Result := 'side-202x386.png'
  else if Width <= 269 then Result := 'side-269x515.png'
  else if Width <= 336 then Result := 'side-336x643.png'
  else Result := 'side-430x824.png';
end;

{ The EXP bar: amber stripes fill a dark track, "EXP 62.00%" on top, like the game's. }
procedure DrawExp(Done: Extended);
var
  C: TCanvas;
  W, H, Fill, X, Step, Edge: Integer;
  Text: String;
  Light: Boolean;
begin
  if ExpBar = nil then
    exit;
  W := ExpBar.Width;
  H := ExpBar.Height;
  ExpBar.Bitmap.Width := W;
  ExpBar.Bitmap.Height := H;
  C := ExpBar.Bitmap.Canvas;
  C.Brush.Style := bsSolid;
  C.Pen.Color := TRACK_EDGE;
  C.Brush.Color := TRACK;
  C.Rectangle(0, 0, W, H);

  if Done < 0 then Done := 0;
  if Done > 1 then Done := 1;
  Edge := ScaleX(2);
  Fill := Round((W - 2 * Edge) * Done);
  Step := ScaleX(6);
  X := 0;
  Light := True;
  while X < Fill do
  begin
    if Light then C.Brush.Color := AMBER_LIGHT else C.Brush.Color := AMBER;
    C.Pen.Color := C.Brush.Color;
    { right to left in Hebrew, like the rest of the window }
    if WizardForm.RightToLeft then
      C.Rectangle(W - Edge - X - Step, Edge, W - Edge - X, H - Edge)
    else
      C.Rectangle(Edge + X, Edge, Edge + X + Step, H - Edge);
    X := X + Step;
    Light := not Light;
  end;
  { cover the last stripe's overshoot }
  C.Brush.Color := TRACK;
  C.Pen.Color := TRACK;
  if Fill < W - 2 * Edge then
    if WizardForm.RightToLeft then
      C.Rectangle(Edge, Edge, W - Edge - Fill, H - Edge)
    else
      C.Rectangle(Edge + Fill, Edge, W - Edge, H - Edge);

  Text := Format('EXP %.2f%%', [Done * 100]);
  C.Brush.Style := bsClear;
  if UsePixelFont() then C.Font.Name := PIXEL_FONT else C.Font.Name := 'Segoe UI';
  C.Font.Size := 9;
  C.Font.Style := [fsBold];
  X := (W - C.TextWidth(Text)) div 2;
  C.Font.Color := clBlack;
  C.TextOut(X + 1, (H - C.TextHeight(Text)) div 2 + 1, Text);
  C.Font.Color := clWhite;
  C.TextOut(X, (H - C.TextHeight(Text)) div 2, Text);
  ExpBar.Invalidate;
end;

{ The desktop box starts as the player chose last time (ticked on a first install). PrepareToInstall
  applies it on silent updates too, so an update keeps that choice, as Inno's own task page did. }
function WantsDesktopIcon(): Boolean;
var
  Prev: String;
begin
  Prev := GetPreviousData('DesktopIcon', '');
  if Prev <> '' then
    Result := Prev = 'yes'
  else if WizardForm.PrevAppDir <> '' then
    { installed by 1.4.0, which didn't record the choice: keep what's on the desktop now }
    Result := FileExists(ExpandConstant('{autodesktop}\{#IconName}.lnk'))
  else
    Result := True;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if DesktopCheck.Checked then
    SetPreviousData(PreviousDataKey, 'DesktopIcon', 'yes')
  else
    SetPreviousData(PreviousDataKey, 'DesktopIcon', 'no');
end;

procedure InitializeWizard();
var
  F: TWizardForm;
  Gap: Integer;
begin
  F := WizardForm;
  ExtractTemporaryFile('DotGothic16-Latin.ttf');
  AddFontResourceEx(ExpandConstant('{tmp}\DotGothic16-Latin.ttf'), FR_PRIVATE, 0);

  StyleHeading(F.WelcomeLabel1);
  { just our text: without Inno's "Click Next to continue" line }
  F.WelcomeLabel2.Caption := SetupMessage(msgWelcomeLabel2);
  StyleBody(F.WelcomeLabel2);
  StyleHeading(F.FinishedHeadingLabel);
  StyleBody(F.FinishedLabel);
  StyleButton(F.NextButton);
  StyleButton(F.BackButton);
  StyleButton(F.CancelButton);

  { the desktop shortcut box sits on the welcome page; its own page is skipped }
  F.WelcomeLabel2.AdjustHeight;
  DesktopCheck := TNewCheckBox.Create(F);
  DesktopCheck.Parent := F.WelcomePage;
  DesktopCheck.Caption := CustomMessage('CreateDesktopIcon');
  DesktopCheck.Left := F.WelcomeLabel2.Left;
  DesktopCheck.Top := F.WelcomeLabel2.Top + F.WelcomeLabel2.Height + ScaleY(14);
  DesktopCheck.Width := F.WelcomeLabel2.Width;
  DesktopCheck.Height := ScaleY(20);
  DesktopCheck.Checked := WantsDesktopIcon();

  { inner pages (Installing, and Preparing if it shows) get the welcome page's layout: the logo
    panel on the side, the page's title and text beside it, no header strip }
  ExtractTemporaryFile(SideArtFor(F.WizardBitmapImage.Width));
  InnerSide := TBitmapImage.Create(F);
  InnerSide.Parent := F.InnerPage;
  InnerSide.SetBounds(F.WizardBitmapImage.Left, F.WizardBitmapImage.Top,
    F.WizardBitmapImage.Width, F.WizardBitmapImage.Height);
  InnerSide.Stretch := True;
  InnerSide.PngImage.LoadFromFile(ExpandConstant('{tmp}\' + SideArtFor(F.WizardBitmapImage.Width)));

  F.MainPanel.Visible := False;
  F.Bevel1.Visible := False;
  F.PageNameLabel.Parent := F.InnerPage;
  F.PageNameLabel.SetBounds(F.WelcomeLabel1.Left, F.WelcomeLabel1.Top, F.WelcomeLabel1.Width, F.WelcomeLabel1.Height);
  StyleHeading(F.PageNameLabel);
  F.PageDescriptionLabel.Parent := F.InnerPage;
  F.PageDescriptionLabel.SetBounds(F.WelcomeLabel2.Left, F.WelcomeLabel2.Top, F.WelcomeLabel2.Width, ScaleY(40));
  StyleBody(F.PageDescriptionLabel);

  Gap := ScaleY(8);
  F.InnerNotebook.SetBounds(F.WelcomeLabel2.Left,
    F.PageDescriptionLabel.Top + F.PageDescriptionLabel.Height + Gap,
    F.WelcomeLabel2.Width,
    F.InnerPage.ClientHeight - (F.PageDescriptionLabel.Top + F.PageDescriptionLabel.Height + Gap) - Gap);

  { the EXP bar takes the progress bar's place }
  ExpBar := TBitmapImage.Create(F);
  ExpBar.Parent := F.InstallingPage;
  ExpBar.SetBounds(F.ProgressGauge.Left, F.ProgressGauge.Top, F.ProgressGauge.Width, ScaleY(20));
  F.ProgressGauge.Visible := False;
  F.FilenameLabel.Visible := False;
  StyleBody(F.StatusLabel);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall)   { Next on Welcome installs }
  else if CurPageID = wpInstalling then
    DrawExp(0)
  else if CurPageID = wpFinished then
  begin
    { our text only (no "Click Finish" line), with Start Companion right under it }
    WizardForm.FinishedLabel.Caption := SetupMessage(msgFinishedLabel);
    WizardForm.FinishedLabel.AdjustHeight;
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(14);
  end;
end;

{ Apply the desktop box right before installing: Inno rebuilds its task list after the welcome page,
  so a choice made earlier would be lost. Runs on silent updates too. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DesktopCheck.Checked then
    WizardSelectTasks('desktopicon')
  else
    WizardSelectTasks('!desktopicon');
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  Done: Extended;
  Step: Integer;
begin
  if MaxProgress <= 0 then
    exit;
  { * 1.0 first: Integer / Integer is a whole-number division in Pascal Script }
  Done := CurProgress * 1.0 / MaxProgress;
  { redraw on every 0.1%, not on every file chunk: fewer repaints, no flicker }
  Step := Round(Done * 1000);
  if Step = ExpStep then
    exit;
  ExpStep := Step;
  DrawExp(Done);
end;

function InitializeUninstall(): Boolean;
begin
  Result := CompanionClosed(UninstallSilent);
end;

function WantsDataDeleted(): Boolean;
begin
  { a silent uninstall keeps the data unless /DELETEDATA is given }
  if HasParam('/DELETEDATA') then
    Result := True
  else if UninstallSilent then
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
