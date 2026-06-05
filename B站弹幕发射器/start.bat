@echo off
title Bilibili Danmaku Sender
cd /d "%~dp0"
start http://localhost:8765
python danmaku_sender.py
pause
