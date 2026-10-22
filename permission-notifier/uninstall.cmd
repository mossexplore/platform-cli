@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1" %*
set "UNINSTALL_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%UNINSTALL_EXIT_CODE%"=="0" (
  echo Uninstallation failed or was cancelled. Review the message above.
) else (
  echo Uninstallation completed. Personal data is kept unless deletion was explicitly confirmed.
)
if not "%PERMISSION_NOTIFIER_NO_PAUSE%"=="1" pause
exit /b %UNINSTALL_EXIT_CODE%
