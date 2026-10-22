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
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) '权限通知助手.lnk'
    if (-not (Test-Path -LiteralPath $shortcutPath)) { throw 'Desktop shortcut was not created' }
    # Read through an ASCII filename too: WScript can lose Chinese filenames
    # on the runner's English Windows, while PowerShell copies them correctly.
    $shortcutProbe = Join-Path $env:RUNNER_TEMP 'notifier-shortcut-probe.lnk'
    try {
        Copy-Item -LiteralPath $shortcutPath -Destination $shortcutProbe -Force
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutProbe)
        if ($shortcut.TargetPath -ne (Join-Path (Split-Path $python) 'pythonw.exe')) { throw 'Shortcut target mismatch' }
        if ($shortcut.Arguments -ne '-m permission_notifier.main') { throw 'Shortcut entry point mismatch' }
    } finally {
        Remove-Item -LiteralPath $shortcutProbe -ErrorAction SilentlyContinue
    }
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
