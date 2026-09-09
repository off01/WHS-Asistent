@echo off
title WHS Asistent
cd /d "%~dp0"
if exist "app\.venv\Scripts\python.exe" goto dependencies
echo Pripravuji WHS Asistenta. Prvni spusteni muze chvili trvat.
py -3 -m venv "app\.venv"
if errorlevel 1 goto fail
:dependencies
"app\.venv\Scripts\python.exe" -c "import selenium, prompt_toolkit" >nul 2>&1
if not errorlevel 1 goto launch
echo Instaluji zavislosti...
"app\.venv\Scripts\python.exe" -m pip install -r "app\requirements.txt"
if errorlevel 1 goto fail
:launch
"app\.venv\Scripts\python.exe" "app\launcher.py"
if errorlevel 1 goto fail
exit /b 0
:fail
echo Spusteni selhalo. Overte instalaci Pythonu 3.10+ a dostupnost balicku.
pause
exit /b 1
