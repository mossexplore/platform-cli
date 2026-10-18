@echo off
py -3 "%~dp0build-demo.py" %*
exit /b %errorlevel%
