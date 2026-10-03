@echo off
chcp 65001 >nul
title JARVIS - Arrêt de l'Agent Local

echo ======================================================================
echo          J.A.R.V.I.S. LOCAL AGENT - ARRÊT DU PROCESSUS
echo ======================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { `
    $stopped = $false; `
    $baseDir = '%~dp0'.TrimEnd('\'); `
    $pidFile = Join-Path $baseDir '.agent_instance.pid'; `
    if (Test-Path $pidFile) { `
        try { `
            $targetPid = [int](Get-Content $pidFile -Raw).Trim(); `
            if ($targetPid -and (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) { `
                Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue; `
                Write-Host ('[✔] Agent local arrêté via PID (' + $targetPid + ')') -ForegroundColor Green; `
                $stopped = $true; `
            } `
        } catch {} `
    } `
    $procs = @(Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }); `
    foreach ($p in $procs) { `
        try { `
            $cmd = (Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $p.Id) -ErrorAction SilentlyContinue).CommandLine; `
            if ($cmd -and ($cmd -like '*jarvis_local_agent.py*')) { `
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; `
                Write-Host ('[✔] Processus agent arrêté (PID: ' + $p.Id + ')') -ForegroundColor Green; `
                $stopped = $true; `
            } `
        } catch {} `
    } `
    if (-not $stopped) { `
        Write-Host '[i] Aucun agent jarvis_local_agent.py n''est actuellement actif.' -ForegroundColor Yellow; `
    } `
    $lockFile = Join-Path $baseDir '.agent_instance.lock'; `
    if (Test-Path $lockFile) { Remove-Item $lockFile -Force -ErrorAction SilentlyContinue } `
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue } `
}"

echo.
echo ======================================================================
ping 127.0.0.1 -n 2 >nul

