@echo off
rem Build Companion.exe (Windows, Python 3.10+). Output: dist\Companion.exe
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --noconsole --name Companion --icon web\logo.ico ^
  --add-data "web;web" --add-data "builds.json;." ^
  --collect-all winocr --collect-submodules winrt --collect-all windows_capture ^
  companion.py
echo.
echo Done: dist\Companion.exe
echo Put it in its own folder. Settings, cache and your data are saved next to it.
pause
