@echo off
title JARVIS - SYNCHRONISATION SESSION GEMINI VERS VPS CLOUD
echo =====================================================================
echo   J.A.R.V.I.S. - SYNCHRONISATION DU PROFIL GEMINI VERS LE VPS
echo =====================================================================
echo.
echo Ce script transfere en toute securite votre profil Chrome connecte
echo vers le serveur Oracle Cloud pour activer la recherche L3 autonome.
echo.

cd /d "%~dp0.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" scripts\deploy_gemini_session_to_vps.py
) else (
    python scripts\deploy_gemini_session_to_vps.py
)

echo.
echo Appuyez sur une touche pour fermer cette fenetre...
pause >nul
