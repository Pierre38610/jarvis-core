@echo off
chcp 65001 >nul
title JARVIS - Installation Démarrage Automatique

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - INSTALLATION AUTOSTART
echo ======================================================================
echo.

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "TARGET_VBS=%BASE_DIR%\start_agent_silent.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JarvisLocalAgent.lnk"

if not exist "%TARGET_VBS%" (
    echo [ERREUR] Le script de lancement "%TARGET_VBS%" est introuvable.
    echo Assurez-vous d'exécuter ce script depuis le dossier racine du projet.
    pause
    exit /b 1
)

echo [*] Dossier racine      : "%BASE_DIR%"
echo [*] Script cible        : "%TARGET_VBS%"
echo [*] Dossier de démarrage: "%STARTUP_FOLDER%"
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = '%TARGET_VBS%'; $sc.WorkingDirectory = '%BASE_DIR%'; $sc.Description = 'Demarrage automatique silencieux de Jarvis Local Agent'; $sc.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [✔] Raccourci de démarrage configuré avec succès !
    echo     Fichier : "%SHORTCUT_PATH%"
    echo.
    echo [*] Démarrage immédiat de l'agent en tâche de fond...
    wscript.exe "%TARGET_VBS%"
    echo [✔] Agent local démarré en arrière-plan [mode 100%% silencieux]
    echo [*] Les logs sont consultables en continu dans :
    echo     "%BASE_DIR%\jarvis_agent.log"
) else (
    echo [ERREUR] Échec de la création du raccourci de démarrage.
)

echo.
echo ======================================================================
echo Installation terminée ! Appuyez sur une touche pour fermer.
pause >nul
