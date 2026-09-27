@echo off
chcp 65001 >nul
title JARVIS - Arrêt de l'Agent Local

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - ARRÊT DU PROCESSUS
echo ======================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessId -ne $PID -and ($_.Name -like 'python*.exe') -and ($_.CommandLine -like '*jarvis_local_agent.py*') }); if ($procs.Count -gt 0) { foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('[✔] Agent local arrêté avec succès (PID: ' + $p.ProcessId + ')') -ForegroundColor Green } } else { Write-Host '[i] Aucun agent jarvis_local_agent.py n''est actuellement actif.' -ForegroundColor Yellow } }"

echo.
echo ======================================================================
ping 127.0.0.1 -n 3 >nul
