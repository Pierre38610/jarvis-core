@echo off
setlocal
echo ======================================================================
echo    COMPILATION ET FLASH DU FIRMWARE J.A.R.V.I.S. ESP32-S3
echo ======================================================================

set PORT=COM5
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%xiaozhi-esp32

cd /d "%PROJECT_DIR%"

echo [1/3] Verification de l'environnement ESP-IDF...
where idf.py >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] idf.py est introuvable dans le PATH.
    echo Veuillez lancer ce script depuis le terminal 'ESP-IDF 5.x PowerShell' ou 'ESP-IDF 5.x Command Prompt'.
    echo Telechargement ESP-IDF : https://dl.espressif.com/dl/esp-idf/
    pause
    exit /b 1
)

echo [2/3] Compilation du firmware pour Waveshare ESP32-S3 Audio (Wake word: Jarvis)...
python scripts/build.py waveshare/esp32-s3-audio-board --wake-word wn9_jarvis_tts --language fr-FR

if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Echec de la compilation.
    pause
    exit /b 1
)

echo.
echo [3/3] Flash du firmware sur %PORT%...
idf.py -p %PORT% flash

echo.
echo [OK] Firmware flashe avec succes !
echo Flash de la partition NVS de configuration...
call "%SCRIPT_DIR%flash_nvs.bat"

echo.
echo ======================================================================
echo  Lancement du moniteur serie (Ctrl+] pour quitter) :
echo ======================================================================
idf.py -p %PORT% monitor
endlocal
