@echo off
REM Move to the directory containing this script
cd /d "%~dp0"

echo ==================================================
echo  Starting Chrome Automation Web Cockpit (Windows)...
echo ==================================================

REM Load .env if present
if exist ".env" (
    for /f "usebackq tokens=*" %%i in (".env") do (
        set "%%i"
    )
)

REM Kill old processes holding port 6969, 9225, 8100, 8181
echo Checking and clearing old processes on ports...
for %%p in (6969 9225 8100 8181) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING') do (
        echo Killing process %%a on port %%p...
        taskkill /f /pid %%a >nul 2>&1
    )
)

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Start Flow Kit Agent server on port 8100 in background
echo Starting Flow Kit Agent server on port 8100...
start "Flow Kit Agent (Port 8100)" /b python -m agent.main

REM Start Lakorn Status Server on port 8181 in background
echo Starting Lakorn Status Server on port 8181...
start "Lakorn Status Server (Port 8181)" /b python scripts\status_server_8181.py

REM Start Uvicorn server on port 6969
echo Starting main Web Cockpit server on port 6969...
uvicorn app.main:app --port 6969 --reload --reload-dir app --reload-dir web --reload-dir agent --reload-include "*.py" --reload-include "*.html" --reload-include "*.js" --reload-include "*.css" --reload-exclude "runtime/*" --reload-exclude "*.bak" --timeout-graceful-shutdown 1
