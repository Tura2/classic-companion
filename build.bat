@echo off
rem Build Companion.exe (Windows, Python 3.10+). Output: dist\Companion.exe
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
rem discord.json (the #shop-sales webhook and the app's client ID) goes in only when it's there
set DISCORD=
if exist discord.json set DISCORD=--add-data "discord.json;."
pyinstaller --noconfirm --onefile --noconsole --name Companion --icon web\logo.ico ^
  --add-data "web;web" --add-data "builds.json;." --add-data "assets;assets" %DISCORD% ^
  --collect-all winocr --collect-submodules winrt --collect-all windows_capture ^
  companion.py
echo.
echo Done: dist\Companion.exe
echo Put it in its own folder. Settings, cache and your data are saved next to it.
pause
