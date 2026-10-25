@echo off
rem Document Merger - launcher: checks Python, installs the libraries once, opens the app.
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python is not installed. Download it from https://www.python.org/downloads/ and check "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".libs_ok" (
  echo Installing the libraries the first time...
  python -m pip install --upgrade pip > install.log 2>&1
  python -m pip install -r requirements.txt >> install.log 2>&1 || (
    echo Could not install the libraries. See install.log.
    pause
    exit /b 1
  )
  echo ok> .libs_ok
)
start "" pythonw "%~dp0DocumentMerger.py"
