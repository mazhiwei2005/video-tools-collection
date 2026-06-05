@echo off
chcp 65001 >nul
title Anime Episode Finder v6
echo Starting Anime Episode Finder v6...
echo Access: http://127.0.0.1:5020
cd /d "%~dp0"
python app.py
pause
