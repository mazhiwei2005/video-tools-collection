@echo off
cd /d "%~dp0"
title Bili Upload Tool

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo Installing dependencies...
pip install bilibili-api-python qrcode[pil] requests pycryptodome aiodns -q 2>nul

echo Starting...
python bili_uploader.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start
    pause
)
