@echo off
setlocal
echo ======================================================================
echo    COMPILATION ET FLASH DU FIRMWARE J.A.R.V.I.S. ESP32-S3
echo ======================================================================

if not "%~1"=="" (
    set PORT=%~1
) else (
    set PORT=COM5
)
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%xiaozhi-esp32

cd /d "%PROJECT_DIR%"

echo [1/3] Verification de l'environnement ESP-IDF...
where idf.py >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Espressif\frameworks\esp-idf-v5.5.5\export.bat" (
        echo [INFO] Activation automatique de ESP-IDF v5.5.5...
        call "C:\Espressif\frameworks\esp-idf-v5.5.5\export.bat"
    ) else if exist "C:\Espressif\frameworks\esp-idf-v5.3.1\export.bat" (
        echo [INFO] Activation automatique de ESP-IDF v5.3.1...
        call "C:\Espressif\frameworks\esp-idf-v5.3.1\export.bat"
    ) else if exist "C:\Espressif\frameworks\esp-idf-v5.3\export.bat" (
        echo [INFO] Activation automatique de ESP-IDF v5.3...
        call "C:\Espressif\frameworks\esp-idf-v5.3\export.bat"
    ) else if exist "C:\Espressif\frameworks\esp-idf\export.bat" (
        echo [INFO] Activation automatique de ESP-IDF...
        call "C:\Espressif\frameworks\esp-idf\export.bat"
    )
)
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

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo [ERREUR] Impossible de flasher sur %PORT%.
    echo Verifications :
    echo  1. Votre carte ESP32-S3 est-elle bien branchee avec un cable USB de DONNEES ?
    echo  2. Le port COM est-il bien %PORT% ?
    echo  3. Mode Bootloader : Maintenez le bouton BOOT, appuyez sur RESET, relachez BOOT.
    echo ======================================================================
    pause
    exit /b 1
)

echo.
echo [OK] Firmware flashe avec succes !
echo [INFO] Les parametres WiFi enregistres dans la NVS sont preserves.
echo.
echo ======================================================================
echo  Lancement du moniteur serie (Ctrl+] pour quitter) :
echo ======================================================================
idf.py -p %PORT% monitor
endlocal
