@echo off
cd /d "%~dp0"
echo ================================
echo   FSDM Anime Downloader
echo   Playwright + Edge + ffmpeg
echo ================================
echo.
pip install playwright requests >nul 2>&1
playwright install chromium >nul 2>&1
python fsdm_downloader.py
pause
