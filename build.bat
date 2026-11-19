@echo off
rem Build Companion's installer (Windows, Python 3.10+, Inno Setup 6). Output: dist\CompanionSetup.exe
rem   build.bat [--no-pause] [--with-discord]
rem Inno Setup, once: winget install JRSoftware.InnoSetup
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller || goto :failed

rem discord.json (the #shop-sales webhook and the app's client ID) goes in only when asked for with
rem --with-discord: a public build never has it, even when the file sits in this folder
set DISCORD=
set PAUSE=1
for %%a in (%*) do (
  if /i "%%a"=="--with-discord" set DISCORD=--add-data "discord.json;."
  if /i "%%a"=="--no-pause" set PAUSE=
)
if defined DISCORD if not exist discord.json (
  echo --with-discord was given, but there's no discord.json here.
  goto :failed
)
if defined DISCORD (echo Building WITH discord.json: a private build, never a release.) else (echo Building without discord.json.)

rem One folder (Companion.exe + _internal\): starts faster than a one-file exe and unpacks nothing
rem into %TEMP%. The installer puts it in place.
pyinstaller --noconfirm --onedir --noconsole --name Companion --icon web\logo.ico --paths app ^
  --add-data "web;web" --add-data "builds.json;." --add-data "assets;assets" %DISCORD% ^
  --collect-all winocr --collect-submodules winrt --collect-all windows_capture ^
  companion.py || goto :failed

for /f %%v in ('python -c "import sys; sys.path.insert(0, 'app'); from version import VERSION; print(VERSION)"') do set VERSION=%%v
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 isn't installed. Install it once with: winget install JRSoftware.InnoSetup
  goto :failed
)
"%ISCC%" /Qp /DAppVersion=%VERSION% installer\companion.iss || goto :failed

echo.
echo Done: dist\CompanionSetup.exe (Companion %VERSION%)
echo Upload it to the release as CompanionSetup.exe: the website's Download buttons point at that name.
if defined PAUSE pause
exit /b 0

:failed
echo.
echo The build failed (see above).
if defined PAUSE pause
exit /b 1
