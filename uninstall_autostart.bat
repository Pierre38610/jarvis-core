@echo off
chcp 65001 >nul
title JARVIS - Désinstallation Autostart

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - DÉSINSTALLATION AUTOSTART
echo ======================================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JarvisLocalAgent.lnk"

if exist "%SHORTCUT_PATH%" (
    del /f /q "%SHORTCUT_PATH%"
    echo [✔] Raccourci supprimé avec succès du démarrage Windows.
) else (
    echo [i] Aucun raccourci n'a été trouvé dans le dossier de démarrage.
)

echo.
echo [*] Arrêt de l'agent local s'il est actif...
call "%~dp0stop_agent.bat"

echo.
echo ======================================================================
echo Désinstallation terminée.
pause
