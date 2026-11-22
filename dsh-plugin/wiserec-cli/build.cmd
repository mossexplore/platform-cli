@echo off
setlocal
title WiseRec DSH Plugin - Build package
pushd "%~dp0..\.."
if errorlevel 1 (
    echo Could not open the platform-cli repository.
    pause
    exit /b 1
)

echo Checking Python 3.11 or newer...
set "wiserec_dsh_python="
py -3 -c "import tomllib" >nul 2>&1
if not errorlevel 1 set "wiserec_dsh_python=py -3"
if not defined wiserec_dsh_python (
    python -c "import tomllib" >nul 2>&1
    if not errorlevel 1 set "wiserec_dsh_python=python"
)
if not defined wiserec_dsh_python (
    echo Python 3.11 or newer was not found. Install it and add it to PATH.
    popd
    pause
    exit /b 1
)

%wiserec_dsh_python% -u "scripts\build_dsh_plugin.py" --output "%~dp0dist" --bundle-only --new-output-directory --verbose
set "wiserec_dsh_exit=%ERRORLEVEL%"
popd
if "%wiserec_dsh_exit%"=="0" (
    echo Build complete. Select the .tgz above in DeepSeek Harness to install the plugin.
) else (
    echo Build failed. See the error above.
)
pause
exit /b %wiserec_dsh_exit%
