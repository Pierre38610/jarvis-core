@echo off
chcp 65001 > nul
title JARVIS - Diagnostic Session Gemini VPS

echo ======================================================================
echo   ✦  J . A . R . V . I . S .   V E R I F I C A T I O N   G E M I N I   V P S  ✦
echo ======================================================================
echo.

cd /d "%~dp0..\.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "%~dp0verifier_session_gemini_vps.py"
) else (
    python "%~dp0verifier_session_gemini_vps.py"
)

echo.
pause
