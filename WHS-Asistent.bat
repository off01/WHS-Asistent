@echo off
setlocal
title WHS Asistent
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
set SE_CACHE_PATH=%~dp0.runtime\selenium
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\bootstrap.ps1"
if errorlevel 1 goto fail
".runtime\venv\Scripts\python.exe" -B "app\launcher.py"
if errorlevel 1 goto fail
exit /b 0
:fail
echo Spusteni selhalo. Podrobnosti jsou uvedene vyse.
pause
exit /b 1
