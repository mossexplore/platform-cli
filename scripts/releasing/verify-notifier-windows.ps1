$ErrorActionPreference = 'Stop'
$archive = @(Get-ChildItem permission-notifier/dist -Filter '*.zip')
if ($archive.Count -ne 1) { throw 'Expected one assistant ZIP' }
$extract = Join-Path $env:RUNNER_TEMP 'notifier-source'
Expand-Archive $archive[0].FullName $extract
$bundle = @(Get-ChildItem $extract -Directory)[0].FullName
$meta = Get-Content "$bundle/release.json" | ConvertFrom-Json
foreach ($script in Get-ChildItem "$bundle/scripts" -Filter '*.ps1') {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw "PowerShell parse failed: $($script.Name)" }
}
# Isolate the installation and config from the runner's ordinary application data.
$originalLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = Join-Path $env:RUNNER_TEMP 'notifier-user'
    & "$bundle/scripts/install.ps1"
    $python = Join-Path $env:LOCALAPPDATA 'Programs/PermissionNotifier/venv/Scripts/python.exe'
    & $python -c "import permission_notifier; assert permission_notifier.__version__ == '$($meta.version)'"
    if ($LASTEXITCODE -ne 0) { throw 'Installed assistant version mismatch' }
    & $python "$bundle/scripts/smoke.py"
    if ($LASTEXITCODE -ne 0) { throw 'Installed assistant HTTP smoke failed' }
    $dataFile = Join-Path $env:LOCALAPPDATA 'PermissionNotifier/upgrade-probe.txt'
    Set-Content $dataFile 'preserve-user-data'
    & "$bundle/scripts/install.ps1"
    if ((Get-Content $dataFile) -ne 'preserve-user-data') { throw 'Reinstall removed user data' }
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
}
