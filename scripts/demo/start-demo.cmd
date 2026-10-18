@echo off
setlocal
set "WISEREC_DEMO_WORKSPACE=%~dp0workspace"
set "ML_CONFIG=%~dp0workspace\config.json"
set "PATH=%~dp0bin;%PATH%"
if not exist "%~dp0bin\ml.cmd" exit /b 1
"%~dp0runtime\Scripts\python.exe" -I -m wiserec_cli_mock.bootstrap context --json >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0workspace"
cmd /d /k
endlocal
