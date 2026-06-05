@echo off
cd /d "%~dp0"
python -c "import flask; import requests; print('OK')"
pause
