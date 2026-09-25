@echo off
title JARVIS - CONNEXION GOOGLE GEMINI (CHROME OFFICIEL)
echo =====================================================================
echo   J.A.R.V.I.S. - CONNEXION GOOGLE GEMINI SANS AUCUN OUTIL AUTOMATISE
echo =====================================================================
echo.
echo Ce script lance Google Chrome officiel natif avec votre profil Jarvis :
echo "%~dp0..\.jarvis_chrome_profile"
echo.
echo Comme il s'agit du vrai Google Chrome sans automation, Google vous
echo autorisera a vous connecter normalement avec votre mot de passe et 2FA.
echo.
echo Une fois connecte sur l'interface de Gemini, fermez simplement Chrome.
echo =====================================================================
echo.

set "PROFILE_DIR=%~dp0..\.jarvis_chrome_profile"
set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

if not exist "%CHROME_EXE%" (
    echo [ERREUR] Google Chrome n'a pas ete trouve dans Program Files.
    echo Veuillez verifier le chemin d'installation de Chrome.
    pause
    exit /b 1
)

echo Ouverture de Google Chrome en cours...
start "" "%CHROME_EXE%" --user-data-dir="%PROFILE_DIR%" --no-first-run --no-default-browser-check "https://gemini.google.com/app"

echo.
echo Google Chrome est ouvert ! Connectez-vous a votre compte Google.
echo Apres avoir ferme Google Chrome, appuyez sur une touche pour terminer.
pause >nul
echo Configuration terminee avec succes !
