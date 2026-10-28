@echo off
rem ============================================================
rem  Portafolio - one-click launcher
rem  Checks everything the apps need and installs what is missing,
rem  without asking the user any technical question:
rem    1. Python 3 (the portfolio)
rem    2. The Python libraries
rem    3. Node.js 22.6 or later (AI Litigation System)
rem    4. Google Chrome (the voice assistants work only in Chrome)
rem  Then starts the portfolio and opens it in Chrome.
rem  Installer details are written to install.log in this folder.
rem ============================================================
setlocal
cd /d "%~dp0"
title Portafolio
set "LOG=%~dp0install.log"
echo.
echo  Portafolio
echo  Checking what this computer needs. Anything missing is installed automatically.
echo  If Windows asks for permission, click "Yes".
echo.

rem ---------- 1. Python ----------
call :find_python
if errorlevel 1 (
    echo  [1/4] Installing Python. This happens only once and takes a few minutes...
    call :install_python
    call :find_python
)
if errorlevel 1 goto fail_python
echo  [1/4] Python ............ OK

rem ---------- 2. Libraries ----------
%PYTHON_CMD% -c "import flask, docx, pypdf, reportlab, PyPDF2, PIL" >nul 2>nul
if errorlevel 1 (
    echo  [2/4] Installing the libraries. This happens only once...
    %PYTHON_CMD% -m pip install --quiet --disable-pip-version-check -r requirements.txt -r escritorio\document_merger\requirements.txt >>"%LOG%" 2>&1
)
%PYTHON_CMD% -c "import flask, docx, pypdf, reportlab, PyPDF2, PIL" >nul 2>nul
if errorlevel 1 goto fail_libraries
echo  [2/4] Libraries ......... OK

rem ---------- 3. Node.js ----------
call :find_node
if errorlevel 1 (
    echo  [3/4] Installing Node.js for AI Litigation System. This happens only once...
    call :install_node
    call :find_node
)
if errorlevel 1 (
    echo  [3/4] Node.js could not be installed. The portfolio opens anyway;
    echo        only AI Litigation System will not start. Details in install.log
) else (
    echo  [3/4] Node.js ........... OK
)

rem ---------- 4. Google Chrome ----------
call :find_chrome
if errorlevel 1 (
    echo  [4/4] Installing Google Chrome for the voice assistants. This happens only once...
    call :install_chrome
    call :find_chrome
)
if errorlevel 1 (
    echo  [4/4] Chrome could not be installed. The portfolio opens in your usual browser,
    echo        but the voice assistants need Chrome. Details in install.log
) else (
    echo  [4/4] Google Chrome ..... OK
)
echo.

rem ---------- Start the portfolio ----------
rem If it is already running, just open the browser.
%PYTHON_CMD% -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1',5000))==0 else 1)"
if not errorlevel 1 goto open_browser

echo  Starting the portfolio...
rem The server window inherits the PATH found above, so it can start Node.js apps.
start "Portafolio - server (close this window to stop the app)" /d "%~dp0web\oficina_virtual" %PYTHON_CMD% app.py

rem Wait up to 30 seconds for the server to answer.
%PYTHON_CMD% -c "import socket,sys,time; ok=any((time.sleep(0.5) or socket.socket().connect_ex(('127.0.0.1',5000))==0) for _ in range(60)); sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo  The portfolio did not answer. Look at the server window for the error.
    pause
    exit /b 1
)

:open_browser
if defined CHROME (
    start "" "%CHROME%" http://127.0.0.1:5000
) else (
    start "" http://127.0.0.1:5000
)
exit /b 0


rem ============================================================
rem  Helpers
rem ============================================================

:find_python
rem "python" may be the Microsoft Store placeholder, so it must actually run.
set "PYTHON_CMD="
rem A Python installed just now may not be in this window's PATH yet: add the usual folders.
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PATH=%%D;%%D\Scripts;%PATH%"
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    exit /b 0
)
exit /b 1

:install_python
call :winget Python.Python.3.12
call :refresh_path
call :find_python
if not errorlevel 1 exit /b 0
rem No winget: download the official installer (per-user, no administrator needed).
set "INST=%TEMP%\python-3.12-installer.exe"
call :download "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" "%INST%"
if exist "%INST%" "%INST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 >>"%LOG%" 2>&1
call :refresh_path
exit /b 0

:find_node
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>22||(a===22&&b>=6)?0:1)" >nul 2>nul
exit /b %errorlevel%

:install_node
call :winget OpenJS.NodeJS.LTS
call :refresh_path
call :find_node
if not errorlevel 1 exit /b 0
rem No winget: download the current LTS installer from nodejs.org.
set "INST=%TEMP%\node-lts-x64.msi"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; $v=(Invoke-RestMethod 'https://nodejs.org/dist/index.json' | Where-Object { $_.lts } | Select-Object -First 1).version; Invoke-WebRequest -UseBasicParsing ('https://nodejs.org/dist/' + $v + '/node-' + $v + '-x64.msi') -OutFile '%INST%'" >>"%LOG%" 2>&1
if exist "%INST%" powershell -NoProfile -Command "Start-Process msiexec -ArgumentList '/i','%INST%','/passive','/norestart' -Verb RunAs -Wait" >>"%LOG%" 2>&1
call :refresh_path
exit /b 0

:find_chrome
set "CHROME="
for %%K in (HKCU HKLM) do (
    if not defined CHROME (
        for /f "tokens=2,*" %%A in ('reg query "%%K\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul ^| find "REG_SZ"') do set "CHROME=%%B"
    )
)
if defined CHROME if exist "%CHROME%" exit /b 0
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if defined CHROME if exist "%CHROME%" exit /b 0
set "CHROME="
exit /b 1

:install_chrome
call :winget Google.Chrome
call :find_chrome
if not errorlevel 1 exit /b 0
rem No winget: Google's official installer.
set "INST=%TEMP%\chrome_installer.exe"
call :download "https://dl.google.com/chrome/install/latest/chrome_installer.exe" "%INST%"
if exist "%INST%" "%INST%" /silent /install >>"%LOG%" 2>&1
exit /b 0

:winget
rem Installs a package silently with winget, when this Windows has it.
where winget >nul 2>nul
if errorlevel 1 exit /b 1
echo ---- winget install %~1 ---- >>"%LOG%"
winget install --id %~1 -e --silent --accept-package-agreements --accept-source-agreements --disable-interactivity >>"%LOG%" 2>&1
exit /b %errorlevel%

:download
echo ---- download %~1 ---- >>"%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing '%~1' -OutFile '%~2'" >>"%LOG%" 2>&1
exit /b %errorlevel%

:refresh_path
rem Re-reads the PATH that the installers just changed, without closing this window.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
exit /b 0


rem ============================================================
rem  Messages when something could not be installed
rem ============================================================

:fail_python
echo.
echo  Python could not be installed automatically.
echo  Check the internet connection and open this file again.
echo  Details were saved in install.log
pause
exit /b 1

:fail_libraries
echo.
echo  The libraries could not be installed.
echo  Check the internet connection and open this file again.
echo  Details were saved in install.log
pause
exit /b 1
