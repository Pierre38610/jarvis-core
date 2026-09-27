@echo off
chcp 65001 >nul
title JARVIS LOCAL AGENT - LOGS EN DIRECT

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - JOURNAL DES ÉVÉNEMENTS
echo ======================================================================
echo.
echo Affichage des 30 dernières lignes et suivi en direct (Ctrl+C pour quitter)...
echo.

set "LOG_FILE=%~dp0jarvis_agent.log"

if not exist "%LOG_FILE%" (
    echo [i] Le fichier jarvis_agent.log n'a pas encore été généré.
    echo Lancez d'abord l'agent via start_agent_silent.vbs ou install_autostart.bat.
    echo.
    pause
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path '%LOG_FILE%' -Tail 30 -Wait"
