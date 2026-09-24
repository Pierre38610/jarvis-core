@echo off
chcp 65001 >nul
title JARVIS CORE SERVER - STARK INDUSTRIES
cd /d "%~dp0"

echo ======================================================================
echo             J.A.R.V.I.S. CORE - INITIALISATION DU SYSTEME
echo ======================================================================
echo.

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERREUR] Environnement virtuel Python 'venv' introuvable.
    pause
    exit /b 1
)

if not exist "%~dp0cloudflared.exe" (
    echo [ERREUR] cloudflared.exe introuvable dans le dossier jarvis-core.
    pause
    exit /b 1
)

taskkill /F /IM cloudflared.exe >nul 2>&1

echo [1/2] Demarrage du backend FastAPI Uvicorn sur le port 8000...
start "JARVIS Backend (FastAPI)" cmd /k "cd /d "%~dp0" && "%~dp0venv\Scripts\python.exe" -m uvicorn App:app --host 0.0.0.0 --port 8000"

echo [2/2] Negociation du Tunnel Securise Cloudflare...
"%~dp0venv\Scripts\python.exe" "%~dp0tunnel_launcher.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Repli vers le tunnel direct Cloudflare...
    "%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000 --protocol http2 --no-prechecks --http-host-header 127.0.0.1:8000
)

pause