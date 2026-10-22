$ErrorActionPreference = 'Stop'
$archive = @(Get-ChildItem permission-notifier/dist -Filter '*.zip')
if ($archive.Count -ne 1) { throw 'Expected one assistant ZIP' }
$extract = Join-Path $env:RUNNER_TEMP 'notifier source with spaces'
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
$originalNoPause = $env:PERMISSION_NOTIFIER_NO_PAUSE
try {
    $env:PERMISSION_NOTIFIER_NO_PAUSE = '1'
    if (-not (Test-Path "$bundle/install.cmd")) { throw 'CMD installer missing from source archive' }
    if (-not (Test-Path "$bundle/uninstall.cmd")) { throw 'CMD uninstaller missing from source archive' }
    # Probe argument forwarding and nonzero exit propagation without running an installation.
    $probe = Join-Path $env:RUNNER_TEMP 'notifier wrapper probe'
    New-Item -ItemType Directory -Force -Path "$probe/scripts" | Out-Null
    Copy-Item "$bundle/install.cmd" "$probe/install.cmd"
    @'
param([switch]$AutoStart, [string]$IndexUrl)
if (-not $AutoStart -or $IndexUrl -ne 'https://example.invalid/path with spaces') { exit 24 }
exit 23
'@ | Set-Content "$probe/scripts/install.ps1" -Encoding ASCII
    & "$probe/install.cmd" -AutoStart -IndexUrl 'https://example.invalid/path with spaces'
    if ($LASTEXITCODE -ne 23) { throw 'CMD installer did not preserve arguments or failure exit code' }
    Copy-Item "$bundle/uninstall.cmd" "$probe/uninstall.cmd"
    @'
param([switch]$DeleteData)
if (-not $DeleteData) { exit 24 }
exit 23
'@ | Set-Content "$probe/scripts/uninstall.ps1" -Encoding ASCII
    & "$probe/uninstall.cmd" -DeleteData
    if ($LASTEXITCODE -ne 23) { throw 'CMD uninstaller did not preserve arguments or failure exit code' }
    $env:LOCALAPPDATA = Join-Path $env:RUNNER_TEMP 'notifier-user'
    & "$bundle/install.cmd"
    if ($LASTEXITCODE -ne 0) { throw 'CMD assistant installation failed' }
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
    & "$bundle/install.cmd"
    if ($LASTEXITCODE -ne 0) { throw 'CMD assistant reinstallation failed' }
    if ((Get-Content $dataFile) -ne 'preserve-user-data') { throw 'Reinstall removed user data' }
    & "$bundle/uninstall.cmd"
    if ($LASTEXITCODE -ne 0) { throw 'CMD assistant uninstallation failed' }
    if (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs/PermissionNotifier')) { throw 'Uninstall left the program directory' }
    if (Test-Path -LiteralPath $shortcutPath) { throw 'Uninstall left the desktop shortcut' }
    if ((Get-Content $dataFile) -ne 'preserve-user-data') { throw 'Default uninstall removed user data' }
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    $env:PERMISSION_NOTIFIER_NO_PAUSE = $originalNoPause
}
