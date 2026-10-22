@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
set "INSTALL_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%INSTALL_EXIT_CODE%"=="0" (
  echo Installation failed. Review the error above.
) else (
  echo Installation completed. Start Permission Notifier from the desktop shortcut.
)
if not "%PERMISSION_NOTIFIER_NO_PAUSE%"=="1" pause
exit /b %INSTALL_EXIT_CODE%
