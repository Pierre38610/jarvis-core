@echo off
chcp 65001 >nul
title JARVIS - CONFIGURATION DOMAINE PERMANENT CLOUDFLARE
cd /d "%~dp0.."
if exist "%~dp0..\venv\Scripts\python.exe" (
    "%~dp0..\venv\Scripts\python.exe" "%~dp0setup_cloudflare_tunnel.py"
) else (
    python "%~dp0setup_cloudflare_tunnel.py"
)
pause
