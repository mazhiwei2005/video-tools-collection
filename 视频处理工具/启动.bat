@echo off
chcp 65001 >nul
cd /d "%~dp0"
python video_processor.py
pause
