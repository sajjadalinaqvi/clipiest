@echo off
setlocal enabledelayedexpansion
title Clipiest Master Studio
echo ============================================================
echo                 CLIPIEST MASTER ENGINE
echo ============================================================

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "VENV_PATH="

REM 1. Check if .venv or venv exists
if exist "%ROOT_DIR%.venv\Scripts\activate.bat" (
    set "VENV_PATH=%ROOT_DIR%.venv"
    goto :ACTIVATE
)
if exist "%ROOT_DIR%venv\Scripts\activate.bat" (
    set "VENV_PATH=%ROOT_DIR%venv"
    goto :ACTIVATE
)
if exist "C:\peakcut\.venv\Scripts\activate.bat" (
    set "VENV_PATH=C:\peakcut\.venv"
    goto :ACTIVATE
)

REM 2. If not found, find Python and create .venv
echo [Clipiest] Virtual environment not found.
echo [Clipiest] Creating virtual environment: .venv ...

set "PY_CMD="
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PY_CMD=python"
    ) else (
        where python3 >nul 2>nul
        if %ERRORLEVEL% equ 0 (
            set "PY_CMD=python3"
        )
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python 3 was not found in PATH!
    echo Please install Python 3.10-3.12 from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [Clipiest] Using Python: %PY_CMD%
%PY_CMD% -m venv "%ROOT_DIR%.venv"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create .venv virtual environment!
    pause
    exit /b 1
)

set "VENV_PATH=%ROOT_DIR%.venv"

:ACTIVATE
echo [Clipiest] Using virtual environment at: %VENV_PATH%
echo [Clipiest] Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment at %VENV_PATH%
    pause
    exit /b 1
)

REM 3. Ensure required packages are installed
python -c "import fastapi, uvicorn" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [Clipiest] Installing required dependencies...
    python -m pip install --upgrade pip
    if exist "%ROOT_DIR%backend\requirements.txt" (
        pip install -r "%ROOT_DIR%backend\requirements.txt"
    ) else if exist "%ROOT_DIR%requirements.txt" (
        pip install -r "%ROOT_DIR%requirements.txt"
    ) else (
        echo [WARNING] No requirements.txt found!
    )
)

REM 4. Launch server with run.py or uvicorn
echo [Clipiest] Launching Clipiest Engine...
cd /d "%ROOT_DIR%backend"

if exist "run.py" (
    python run.py
) else (
    python -m uvicorn clipiest.server:app --host 127.0.0.1 --port 8780
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [Clipiest] Server stopped with exit code %ERRORLEVEL%.
)
pause
