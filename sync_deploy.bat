@echo off
chcp 65001 >nul
title JARVIS SYNC & CLOUD DEPLOY
cd /d "%~dp0"

"%~dp0venv\Scripts\python.exe" "%~dp0sync_deploy.py" -m "%~1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Une erreur est survenue lors de la synchronisation.
    pause
)
