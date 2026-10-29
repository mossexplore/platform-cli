$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .. -e .
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed' }
if (!(Test-Path config.local.json)) { Copy-Item config.example.json config.local.json }
Write-Host 'Fill config.local.json, create the MySQL database, then run migrate and start.ps1. Microsoft Edge must be installed.'
