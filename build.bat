@echo off
rem Build Companion's installer (Windows, Python 3.10+, Inno Setup 6). Output: dist\CompanionSetup.exe
rem Inno Setup, once: winget install JRSoftware.InnoSetup
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller || goto :failed

rem discord.json (the #shop-sales webhook and the app's client ID) goes in only when it's there
set DISCORD=
if exist discord.json set DISCORD=--add-data "discord.json;."

rem One folder (Companion.exe + _internal\): starts faster than a one-file exe and unpacks nothing
rem into %TEMP%. The installer puts it in place.
pyinstaller --noconfirm --onedir --noconsole --name Companion --icon web\logo.ico ^
  --add-data "web;web" --add-data "builds.json;." --add-data "assets;assets" %DISCORD% ^
  --collect-all winocr --collect-submodules winrt --collect-all windows_capture ^
  companion.py || goto :failed

for /f %%v in ('python -c "from version import VERSION; print(VERSION)"') do set VERSION=%%v
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
if not "%1"=="--no-pause" pause
exit /b 0

:failed
echo.
echo The build failed (see above).
if not "%1"=="--no-pause" pause
exit /b 1
