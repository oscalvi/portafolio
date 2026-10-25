@echo off
setlocal
cd /d "%~dp0"

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

echo Checking dependencies...
%PYTHON_CMD% -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo Installing required packages ^(this only happens once^)...
    %PYTHON_CMD% -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Could not install the required packages. Check your internet
        echo connection and try again.
        pause
        exit /b 1
    )
)

echo Starting EmailMover...
start "EmailMover Server" %PYTHON_CMD% app.py
timeout /t 2 /nobreak >nul
start "" http://localhost:5000
