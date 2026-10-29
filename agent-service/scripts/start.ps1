$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m app.manage serve --config config.local.json
exit $LASTEXITCODE
