@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-install.ps1" %*
set "BUILD_INSTALL_RESULT=%ERRORLEVEL%"
if not "%BUILD_INSTALL_RESULT%"=="0" (
  echo.
  echo Build or installation failed. Review the error above.
)
exit /b %BUILD_INSTALL_RESULT%
