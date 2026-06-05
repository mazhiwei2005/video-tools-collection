@echo off
cd /d "%~dp0"

echo ========================================
echo   AI Subtitle Studio v1.0
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

REM Check translators
python -c "import translators" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing translators...
    pip install translators
)

REM Check faster-whisper
python -c "import faster_whisper" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing faster-whisper...
    pip install faster-whisper
)

REM Check torch
python -c "import torch" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing torch...
    pip install torch --index-url https://download.pytorch.org/whl/cu121
)

echo.
echo Starting...
echo.
python main.py 2>error.log

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start
    echo.
    echo Error log:
    type error.log
    pause
)
