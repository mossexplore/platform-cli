@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
    echo Could not open the cli-go directory.
    pause
    exit /b 1
)

if not exist "config.json" (
    echo Missing cli-go\config.json. Prepare it using the instructions in cli-go\README.md.
    popd
    pause
    exit /b 1
)

if not defined GOMODCACHE if exist "dist\go-module-cache\cache\download\" (
    set "GOMODCACHE=%CD%\dist\go-module-cache"
)

call ".\scripts\build-release.cmd" -ConfigPath ".\config.json" -NewOutputDirectory
set "wiserec_build_exit=%ERRORLEVEL%"
popd
if not "%wiserec_build_exit%"=="0" echo Build failed. See the error above.
pause
exit /b %wiserec_build_exit%
