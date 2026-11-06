@echo off
cd /d "%~dp0"
echo Starting Random Play workbench: http://127.0.0.1:5000
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0run_web.py" --open-browser
pause
