@echo off
rem Build Companion's installer (Windows, Python 3.10+, Inno Setup 6). Output: dist\CompanionSetup.exe
rem   build.bat [--no-pause] [--with-reports]
rem Inno Setup, once: winget install JRSoftware.InnoSetup
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller || goto :failed

rem reports.json (the report server's address and upload key) goes in only when asked for with
rem --with-reports. Releases are built with it: it turns on problem reports and Discord, both off
rem until the player switches them on. The key is public in practice (it's in the exe); the server's
rem caps are the guard, and the Discord webhook and GitHub token stay on the server.
set REPORTS=
set PAUSE=1
for %%a in (%*) do (
  if /i "%%a"=="--with-reports" set REPORTS=--add-data "reports.json;."
  if /i "%%a"=="--no-pause" set PAUSE=
)
if defined REPORTS if not exist reports.json (
  echo --with-reports was given, but there's no reports.json here.
  goto :failed
)
if defined REPORTS (echo Building WITH reports.json: problem reports and Discord work.) else (echo Building without reports.json: no problem reports, no Discord.)

rem One folder (Companion.exe + _internal\): starts faster than a one-file exe and unpacks nothing
rem into %TEMP%. The installer puts it in place.
pyinstaller --noconfirm --onedir --noconsole --name Companion --icon web\logo.ico --paths app ^
  --add-data "web;web" --add-data "builds.json;." --add-data "assets;assets" %REPORTS% ^
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
