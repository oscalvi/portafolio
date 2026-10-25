@echo off
rem ============================================================
rem  Portafolio - one-click launcher
rem  1. Checks that Python is installed.
rem  2. Installs the libraries the first time (or when one is missing).
rem  3. Starts the web app and opens it in the browser.
rem ============================================================
setlocal
cd /d "%~dp0"
title Portafolio

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python was not found on this computer.
        echo Please install Python 3 from https://www.python.org/downloads/
        echo ^(tick "Add python.exe to PATH" during setup^), then run this again.
        pause
        exit /b 1
    ) else (
        set "PYTHON_CMD=py"
    )
) else (
    set "PYTHON_CMD=python"
)

echo Checking libraries...
%PYTHON_CMD% -c "import flask, docx, pypdf, reportlab, PyPDF2, PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing the libraries ^(this only happens once^)...
    %PYTHON_CMD% -m pip install --quiet --disable-pip-version-check -r requirements.txt -r escritorio\document_merger\requirements.txt
    if errorlevel 1 (
        echo.
        echo Could not install the libraries. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

rem If the app is already running, just open the browser.
%PYTHON_CMD% -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1',5000))==0 else 1)"
if not errorlevel 1 goto abrir

echo Starting the app...
start "Portafolio - server (close this window to stop the app)" /d "%~dp0web\oficina_virtual" %PYTHON_CMD% app.py

rem Wait up to 30 seconds for the server to answer.
%PYTHON_CMD% -c "import socket,sys,time; ok=any((time.sleep(0.5) or socket.socket().connect_ex(('127.0.0.1',5000))==0) for _ in range(60)); sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo The app did not answer. Look at the server window for the error.
    pause
    exit /b 1
)

:abrir
start "" http://127.0.0.1:5000
exit /b 0
