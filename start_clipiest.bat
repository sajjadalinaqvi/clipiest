@echo off
title Clipiest Master Studio
echo Starting Clipiest...
cd /d "%~dp0\backend"

if exist "C:\peakcut\.venv\Scripts\python.exe" (
    "C:\peakcut\.venv\Scripts\python.exe" run.py
) else if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" run.py
) else (
    python run.py
)
pause
