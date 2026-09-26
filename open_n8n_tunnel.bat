@echo off
chcp 65001 >nul
title J.A.R.V.I.S. - Tunnel Sécurisé n8n
cd /d "%~dp0"

echo ======================================================================
echo    ✦ J.A.R.V.I.S. - OUVERTURE DU TUNNEL N8N (LOCAL 5678) ✦
echo ======================================================================
echo.
echo Connexion au VPS (158.178.206.213) et redirection du port 5678...
echo Une fois connecte, ouvrez simplement votre navigateur sur :
echo http://localhost:5678
echo.
echo (Laissez cette fenetre ouverte tant que vous utilisez n8n)
echo.

ssh -i ".\clés ssh\ssh-key-2026-09-25.key" -N -L 5678:127.0.0.1:5678 opc@158.178.206.213
pause
