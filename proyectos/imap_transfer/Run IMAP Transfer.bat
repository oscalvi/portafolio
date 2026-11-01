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

where pythonw >nul 2>nul
if errorlevel 1 (
    if "%PYTHON_CMD%"=="py" (
        set "PYTHONW_CMD=py -w"
    ) else (
        set "PYTHONW_CMD=%PYTHON_CMD%"
    )
) else (
    set "PYTHONW_CMD=pythonw"
)

start "" %PYTHONW_CMD% config_gui.py
