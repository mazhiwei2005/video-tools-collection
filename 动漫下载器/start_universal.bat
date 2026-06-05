@echo off
cd /d "%~dp0"
echo ================================
echo   Universal Anime Downloader
echo   Playwright + Edge + ffmpeg
echo ================================
echo.
pip install playwright requests >nul 2>&1
playwright install chromium >nul 2>&1
python universal_downloader.py
if errorlevel 1 (
    echo.
    echo [ERROR] Start failed
    echo   1. pip install playwright
    echo   2. playwright install chromium
    echo.
)
pause
