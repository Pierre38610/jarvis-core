@echo off
title JARVIS - CONNEXION AMAZON SEND TO KINDLE
echo =====================================================================
echo   J.A.R.V.I.S. - SESSION AMAZON SEND TO KINDLE
echo =====================================================================
echo.
echo Ce script ouvre Google Chrome officiel avec votre profil Jarvis :
echo "%~dp0..\.jarvis_chrome_profile"
echo directement sur la page Amazon Send to Kindle :
echo https://www.amazon.fr/sendtokindle
echo.
echo Une fois connecte a votre compte Amazon, Jarvis pourra deposer et
echo envoyer automatiquement tous vos fichiers vers votre liseuse Kindle !
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

echo Ouverture d'Amazon Send to Kindle dans Google Chrome...
start "" "%CHROME_EXE%" --user-data-dir="%PROFILE_DIR%" --no-first-run --no-default-browser-check "https://www.amazon.fr/sendtokindle"

echo.
echo Google Chrome est ouvert sur Amazon Send to Kindle !
echo Verifiez votre connexion ou connectez-vous, puis fermez Chrome.
echo.
pause
