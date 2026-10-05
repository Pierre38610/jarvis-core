@echo off
setlocal
echo ======================================================================
echo    FLASH DE LA PARTITION NVS J.A.R.V.I.S. (TOKEN + WEBSOCKET)
echo ======================================================================

if not "%~1"=="" (
    set PORT=%~1
) else (
    set PORT=COM5
)
set BAUD=460800
set SCRIPT_DIR=%~dp0
set NVS_BIN=%SCRIPT_DIR%nvs_jarvis.bin
set NVS_CSV=%SCRIPT_DIR%nvs_jarvis.csv

if not exist "%NVS_CSV%" (
    if exist "%SCRIPT_DIR%nvs_jarvis.csv.example" (
        echo [INFO] Fichier nvs_jarvis.csv non trouve.
        echo Veuillez creer firmware_esp32/nvs_jarvis.csv a partir de firmware_esp32/nvs_jarvis.csv.example
        echo en y renseignant votre token JWT d'appareil.
        exit /b 1
    )
)

if not exist "%NVS_BIN%" (
    echo [INFO] Generation du binaire NVS...
    python -m esp_idf_nvs_partition_gen generate "%NVS_CSV%" "%NVS_BIN%" 0x6000
)

echo Port : %PORT%
echo Fichier NVS : %NVS_BIN%
echo.
echo Flash de la partition NVS a l'adresse 0x9000...
python -m esptool --port %PORT% --baud %BAUD% write_flash 0x9000 "%NVS_BIN%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Partition NVS flashee avec succes sur %PORT% !
) else (
    echo.
    echo [ERREUR] Echec du flash NVS.
    echo Si le port COM5 est occupe, fermez tout moniteur serie ou terminal ouvert sur COM5.
)
endlocal
