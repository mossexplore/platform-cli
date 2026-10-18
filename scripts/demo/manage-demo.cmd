@echo off
"%~dp0runtime\Scripts\python.exe" -I -m wiserec_cli_mock.manage --workspace "%~dp0workspace" %*
exit /b %errorlevel%
