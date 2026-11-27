@echo off
setlocal
set "build_python="
py -3 -c "import tomllib" >nul 2>&1
if not errorlevel 1 set "build_python=py -3"
if not defined build_python (
    python -c "import tomllib" >nul 2>&1
    if not errorlevel 1 set "build_python=python"
)
if not defined build_python (
    echo Python 3.11 or newer is required to build the platform Skill ZIP.
    pause
    exit /b 1
)

%build_python% "%~dp0build.py" %*
set "build_result=%ERRORLEVEL%"
if not "%build_result%"=="0" echo Platform Skill packaging failed. See the error above.
pause
exit /b %build_result%
