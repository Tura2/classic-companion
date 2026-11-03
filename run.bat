@echo off
rem Run Companion from source (needs Python 3.10+ from python.org)
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python companion.py
pause
