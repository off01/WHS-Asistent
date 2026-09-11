@echo off
setlocal
title WHS Asistent
cd /d "%~dp0"
if not exist "%~dp0app\bootstrap.ps1" goto incomplete
if not exist "%~dp0app\launcher.py" goto incomplete
set PYTHONDONTWRITEBYTECODE=1
set SE_CACHE_PATH=%~dp0.runtime\selenium
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\bootstrap.ps1"
if errorlevel 1 goto fail
if not exist ".runtime\venv\Scripts\python.exe" goto fail
".runtime\venv\Scripts\python.exe" -B "app\launcher.py"
if errorlevel 1 goto fail
exit /b 0
:incomplete
echo Chybi slozka app nebo je balicek neuplny.
echo Rozbalte cely ZIP. WHS-Asistent.bat a slozka app musi byt vedle sebe.
echo Samotny soubor BAT nestaci. Pro zastupce ponechte puvodni soubory na miste.
pause
exit /b 1
:fail
echo Spusteni selhalo. Podrobnosti jsou uvedene vyse.
pause
exit /b 1
