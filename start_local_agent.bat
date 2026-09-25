@echo off
chcp 65001 >nul
title JARVIS LOCAL AGENT - PC COMPANION
cd /d "%~dp0"

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - PC COMPANION
echo ======================================================================
echo.

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERREUR] Python venv introuvable.
    pause
    exit /b 1
)

"%~dp0venv\Scripts\python.exe" -u "%~dp0jarvis_local_agent.py"

pause
