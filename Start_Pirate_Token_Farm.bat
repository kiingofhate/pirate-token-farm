@echo off
chcp 65001 >nul
title Pirate Token Farm Launcher
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

where pyw >nul 2>&1 && (
    start "" pyw -3 "%~dp0fortnite_farm.py"
    exit /b
)
where pythonw >nul 2>&1 && (
    start "" pythonw "%~dp0fortnite_farm.py"
    exit /b
)
where python >nul 2>&1 && (
    start "" python "%~dp0fortnite_farm.py"
    exit /b
)

echo Python 3.10+ not found in PATH. Download standalone .exe from GitHub Releases or install Python.
pause
