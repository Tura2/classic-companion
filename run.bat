@echo off
rem Run Companion from source (needs Python 3.10+ from python.org). Companion opens its own
rem window, so it starts with pythonw, which has no console; this window closes by itself.
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Installing what Companion needs failed. Check the internet connection and try again.
  pause
  exit /b 1
)
start "" pythonw companion.py
