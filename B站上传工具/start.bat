@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo ============================================
echo   Bilibili Upload Tool (Playwright)
echo ============================================
echo.
python bili_browser_uploader.py
