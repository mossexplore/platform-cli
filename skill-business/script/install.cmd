@echo off
setlocal
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "install_result=%ERRORLEVEL%"
if not "%install_result%"=="0" echo Business Skill installation failed. See the error above.
pause
exit /b %install_result%
