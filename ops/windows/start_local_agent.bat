@echo off
chcp 65001 >nul
title JARVIS LOCAL AGENT - PC COMPANION
cd /d "%~dp0..\.."

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - PC COMPANION
echo ======================================================================
echo.

set "ROOT_DIR=%~dp0..\.."
if not exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    echo [ERREUR] Python venv introuvable dans %ROOT_DIR%\venv.
    pause
    exit /b 1
)

"%ROOT_DIR%\venv\Scripts\python.exe" -u "%~dp0jarvis_local_agent.py"

pause
