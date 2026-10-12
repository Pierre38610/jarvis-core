@echo off
chcp 65001 >nul
title JARVIS - Installation Démarrage Automatique

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - INSTALLATION AUTOSTART
echo ======================================================================
echo.

set "OPS_DIR=%~dp0"
if "%OPS_DIR:~-1%"=="\" set "OPS_DIR=%OPS_DIR:~0,-1%"
for %%I in ("%OPS_DIR%\..\..") do set "ROOT_DIR=%%~fI"

set "TARGET_VBS=%OPS_DIR%\start_agent_silent.vbs"
if not exist "%TARGET_VBS%" set "TARGET_VBS=%ROOT_DIR%\start_agent_silent.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JarvisLocalAgent.lnk"

if not exist "%TARGET_VBS%" (
    echo [ERREUR] Le script de lancement "%TARGET_VBS%" est introuvable.
    pause
    exit /b 1
)

echo [*] Dossier racine      : "%ROOT_DIR%"
echo [*] Script cible        : "%TARGET_VBS%"
echo [*] Dossier de démarrage: "%STARTUP_FOLDER%"
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = '%TARGET_VBS%'; $sc.WorkingDirectory = '%ROOT_DIR%'; $sc.Description = 'Demarrage automatique silencieux de Jarvis Local Agent'; $sc.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [✔] Raccourci de démarrage configuré avec succès !
    echo     Fichier : "%SHORTCUT_PATH%"
    echo.
    echo [*] Démarrage immédiat de l'agent en tâche de fond...
    wscript.exe "%TARGET_VBS%"
    echo [✔] Agent local démarré en arrière-plan [mode 100%% silencieux]
    echo [*] Les logs sont consultables en continu dans :
    echo     "%ROOT_DIR%\jarvis_agent.log"
) else (
    echo [ERREUR] Échec de la création du raccourci de démarrage.
)

echo.
echo ======================================================================
echo Installation terminée ! Appuyez sur une touche pour fermer.
pause >nul
