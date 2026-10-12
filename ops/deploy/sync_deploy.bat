@echo off
chcp 65001 >nul
title JARVIS SYNC & CLOUD DEPLOY
cd /d "%~dp0..\.."

if exist "%~dp0..\..\venv\Scripts\python.exe" (
    "%~dp0..\..\venv\Scripts\python.exe" "%~dp0sync_deploy.py" -m "%~1"
) else (
    python "%~dp0sync_deploy.py" -m "%~1"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Une erreur est survenue lors de la synchronisation.
    pause
)
