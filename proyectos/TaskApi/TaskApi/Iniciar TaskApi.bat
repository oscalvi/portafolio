@echo off
rem TaskApi: starts the API and opens Swagger in the browser to try it.
rem Needs the .NET 10 SDK (installs it with winget if missing).
title TaskApi
cd /d "%~dp0TaskApi"

where dotnet >nul 2>nul
if errorlevel 1 goto instalar
dotnet --list-sdks | findstr /b "10." >nul
if not errorlevel 1 goto correr

:instalar
echo No encuentro el SDK de .NET 10. Lo instalo con winget...
winget install --id Microsoft.DotNet.SDK.10 -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo No se pudo instalar. Descarguelo de https://dotnet.microsoft.com/download/dotnet/10.0
  pause
  exit /b 1
)
echo Cierre esta ventana y vuelva a abrir "Iniciar TaskApi.bat".
pause
exit /b 0

:correr
echo TaskApi se esta iniciando. Se abrira http://localhost:5079/swagger
echo Para detenerla, cierre esta ventana o presione Ctrl+C.
start "" cmd /c "timeout /t 8 >nul & start http://localhost:5079/swagger"
set ASPNETCORE_ENVIRONMENT=Development
set ASPNETCORE_URLS=http://localhost:5079
dotnet run --no-launch-profile
pause
