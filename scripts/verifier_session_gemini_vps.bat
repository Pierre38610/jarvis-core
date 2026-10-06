@echo off
chcp 65001 > nul
title JARVIS - Diagnostic Session Gemini VPS

echo ======================================================================
echo   ✦  J . A . R . V . I . S .   V E R I F I C A T I O N   G E M I N I   V P S  ✦
echo ======================================================================
echo.

if exist "..\venv\Scripts\python.exe" (
    "..\venv\Scripts\python.exe" verifier_session_gemini_vps.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" scripts\verifier_session_gemini_vps.py
) else (
    python scripts\verifier_session_gemini_vps.py
)

echo.
pause
