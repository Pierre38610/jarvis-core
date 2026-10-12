@echo off
chcp 65001 >nul
title JARVIS CORE SERVER - STARK INDUSTRIES
cd /d "%~dp0..\.."

echo ======================================================================
echo             J.A.R.V.I.S. CORE - INITIALISATION DU SYSTEME
echo ======================================================================
echo.

set "ROOT_DIR=%~dp0..\.."
set "CLOUDFLARED_BIN=%~dp0..\deploy\cloudflared.exe"
if not exist "%CLOUDFLARED_BIN%" set "CLOUDFLARED_BIN=%ROOT_DIR%\cloudflared.exe"

if not exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    echo [ERREUR] Environnement virtuel Python 'venv' introuvable.
    pause
    exit /b 1
)

if not exist "%CLOUDFLARED_BIN%" (
    echo [ERREUR] cloudflared.exe introuvable (recherche dans ops/deploy/ et racine).
    pause
    exit /b 1
)

taskkill /F /IM cloudflared.exe >nul 2>&1

echo [1/2] Demarrage du backend FastAPI Uvicorn sur le port 8000...
start "JARVIS Backend (FastAPI)" cmd /k "cd /d "%ROOT_DIR%" && "%ROOT_DIR%\venv\Scripts\python.exe" -m uvicorn backend.App:app --host 0.0.0.0 --port 8000"

echo [2/2] Negociation du Tunnel Securise Cloudflare...
"%ROOT_DIR%\venv\Scripts\python.exe" "%~dp0tunnel_launcher.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Repli vers le tunnel direct Cloudflare...
    "%CLOUDFLARED_BIN%" tunnel --url http://127.0.0.1:8000 --protocol http2 --no-prechecks --http-host-header 127.0.0.1:8000
)

pause