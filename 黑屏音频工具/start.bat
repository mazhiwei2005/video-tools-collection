@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
python black_screen_maker.py
if errorlevel 1 (
    echo.
    echo [ERROR] Python not found or script error.
    pause
)
