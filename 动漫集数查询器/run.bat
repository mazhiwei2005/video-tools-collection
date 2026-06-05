@echo off
cd /d "%~dp0"
python app.py > log.txt 2>&1
