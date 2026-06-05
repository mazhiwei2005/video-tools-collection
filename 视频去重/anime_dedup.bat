@echo off
setlocal enabledelayedexpansion
set "BD=%~dp0"
pushd "!BD!"
pythonw "anime_dedup.py"
if errorlevel 1 (
    python "anime_dedup.py"
    pause
)
popd
