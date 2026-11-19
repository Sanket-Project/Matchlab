@echo off
cd /d "%~dp0"
echo ========================================================
echo MatchLab: Checking today's sports matches online...
echo ========================================================
".venv\Scripts\python.exe" tools\fetch_today_matches.py
echo.
echo Starting MatchLab local sports dashboard...
".venv\Scripts\python.exe" app.py --port 8766 --open
if errorlevel 1 pause
