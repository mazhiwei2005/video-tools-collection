@echo off
echo ============================================
echo   Starting Edge with Debug Mode...
echo   Close all Edge windows first!
echo ============================================
echo.
taskkill /f /im msedge.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
echo Edge started with debug port 9222
echo You can now close this window.
timeout /t 5 /nobreak >nul
