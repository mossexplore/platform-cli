@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m app.manage serve --config config.local.json
exit /b %errorlevel%
