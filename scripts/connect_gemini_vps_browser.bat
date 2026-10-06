@echo off
title JARVIS - CONNEXION GOOGLE GEMINI VPS CLOUD (NAVIGATEUR)
echo =====================================================================
echo   J.A.R.V.I.S. - CONNEXION DIRECTE GOOGLE GEMINI SUR LE VPS
echo =====================================================================
echo.
echo Ce script ouvre directement Google Chrome distant dans votre navigateur
echo pour vous permettre de vous authentifier sans aucun logiciel a installer.
echo.

cd /d "%~dp0.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" scripts\connect_gemini_vps_browser.py
) else (
    python scripts\connect_gemini_vps_browser.py
)

echo.
echo Appuyez sur une touche pour fermer cette fenetre...
pause >nul
