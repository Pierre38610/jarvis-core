@echo off
chcp 65001 >nul
title CONFIGURATION TUNNEL CLOUDFLARE PERMANENT - J.A.R.V.I.S.
cd /d "%~dp0"

"%~dp0venv\Scripts\python.exe" "%~dp0setup_cloudflare_tunnel.py"

pause
