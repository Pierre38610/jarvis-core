@echo off
chcp 65001 >nul
title J.A.R.V.I.S. - Tunnel Sécurisé n8n
cd /d "%~dp0"

echo ======================================================================
echo    ✦ J.A.R.V.I.S. - OUVERTURE DU TUNNEL N8N (LOCAL 5678) ✦
echo ======================================================================
echo.
if "%JARVIS_VPS_HOST%"=="" set JARVIS_VPS_HOST=158.178.206.213
if "%JARVIS_VPS_USER%"=="" set JARVIS_VPS_USER=opc

set SSH_KEY=.\clés ssh\ssh-key-2026-09-25.key
if not exist "%SSH_KEY%" set SSH_KEY=.\cles ssh\ssh-key-2026-09-25.key
if not exist "%SSH_KEY%" set SSH_KEY=%USERPROFILE%\.ssh\ssh-key-2026-09-25.key
if not exist "%SSH_KEY%" set SSH_KEY=%USERPROFILE%\.ssh\id_rsa

echo Connexion au VPS (%JARVIS_VPS_HOST%) et redirection du port 5678...
echo Une fois connecte, ouvrez simplement votre navigateur sur :
echo http://localhost:5678
echo.
echo (Laissez cette fenetre ouverte tant que vous utilisez n8n)
echo.

if exist "%SSH_KEY%" (
    ssh -i "%SSH_KEY%" -N -L 5678:127.0.0.1:5678 %JARVIS_VPS_USER%@%JARVIS_VPS_HOST%
) else (
    ssh -N -L 5678:127.0.0.1:5678 %JARVIS_VPS_USER%@%JARVIS_VPS_HOST%
)
pause
