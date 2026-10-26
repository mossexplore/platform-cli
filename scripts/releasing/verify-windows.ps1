$ErrorActionPreference = 'Stop'
$version = (Select-String -Path pyproject.toml -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value
foreach ($mode in @('online', 'offline')) {
    $zip = @(Get-ChildItem release -Filter "*-$mode.zip")
    if ($zip.Count -ne 1) { throw "Expected one $mode archive" }
    $extract = Join-Path $env:RUNNER_TEMP "verify-$mode"
    Expand-Archive $zip[0].FullName $extract
    $bundle = @(Get-ChildItem $extract -Directory)[0].FullName
    $install = Join-Path $env:RUNNER_TEMP "cli-$mode"
    if ($mode -eq 'offline') {
        $env:PIP_NO_INDEX = '1'
        $env:PIP_INDEX_URL = 'http://127.0.0.1:9/unavailable'
        $env:PIP_NO_CACHE_DIR = '1'
    }
    & "$bundle/install.ps1" -InstallDirectory $install
    $exe = Join-Path $install 'venv/Scripts/ml.exe'
    if (-not (Test-Path $exe)) { $exe = Join-Path $install '.venv/Scripts/ml.exe' }
    $actual = & $exe --version
    if ($LASTEXITCODE -ne 0 -or $actual -notmatch "ml $version") { throw "Version check failed: $actual" }
    & $exe --help
    if ($LASTEXITCODE -ne 0) { throw 'Help failed' }
    $installedPython = Join-Path $install 'venv/Scripts/python.exe'
    $modulePath = (& $installedPython -c 'import wiserec_cli; print(wiserec_cli.__file__)' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $modulePath)) { throw 'Installed CLI package was not found' }
    & $installedPython -c "from wiserec_cli.config import ConfigManager; ConfigManager().use_profile('test')"
    if ($LASTEXITCODE -ne 0) { throw 'Selecting environment before reinstall failed' }
    Add-Content -LiteralPath $modulePath -Value '# same-version-reinstall-probe'
    & "$bundle/install.ps1" -InstallDirectory $install
    if (Select-String -LiteralPath $modulePath -Pattern 'same-version-reinstall-probe' -Quiet) {
        throw 'Same-version installation did not replace the CLI Wheel'
    }
    & $installedPython -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
    if ($LASTEXITCODE -ne 0) { throw 'Same-version reinstall changed selected environment' }

    # Source directories on PYTHONPATH must not override the bundle during install or ml.cmd startup.
    $shadow = Join-Path $env:RUNNER_TEMP "cli-shadow-$mode"
    New-Item -ItemType Directory -Path "$shadow/wiserec_cli" -Force | Out-Null
    Set-Content -LiteralPath "$shadow/wiserec_cli/__init__.py" -Encoding ASCII -Value "raise RuntimeError('source-shadow-probe')"
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $shadow
        & "$bundle/install.ps1" -InstallDirectory $install
        $launcher = Join-Path $install 'bin/ml.cmd'
        $isolatedVersion = & $launcher --version
        if ($LASTEXITCODE -ne 0 -or $isolatedVersion -notmatch "ml $version") {
            throw 'PYTHONPATH overrode the installed CLI launcher'
        }
        & $installedPython -I -c "from importlib.metadata import version; import wiserec_cli; assert version('wiserec-cli') == wiserec_cli.__version__ == '$version'"
        if ($LASTEXITCODE -ne 0) { throw 'Installed metadata and imported CLI versions differ' }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
    }

    # Recover from leftover metadata without requiring the user to pass -Force.
    $backupsBefore = @(Get-ChildItem -LiteralPath $install -Directory -Filter 'venv-backup-*').Count
    $extraMetadata = Join-Path $install 'venv/Lib/site-packages/wiserec_cli-0.0.1.dist-info'
    New-Item -ItemType Directory -Path $extraMetadata -Force | Out-Null
    Set-Content -LiteralPath "$extraMetadata/METADATA" -Encoding ASCII -Value "Name: wiserec-cli`nVersion: 0.0.1`n"
    & "$bundle/install.ps1" -InstallDirectory $install
    $backupsAfter = @(Get-ChildItem -LiteralPath $install -Directory -Filter 'venv-backup-*').Count
    if ($backupsAfter -ne ($backupsBefore + 1)) { throw 'Duplicate metadata did not trigger one backed-up rebuild' }
    & $installedPython -I -c "from importlib.metadata import version; import wiserec_cli; assert version('wiserec-cli') == wiserec_cli.__version__ == '$version'"
    if ($LASTEXITCODE -ne 0) { throw 'Version verification after automatic repair failed' }

    # Reproduce an existing venv pointing at a removed base Python.
    $venvConfig = Join-Path $install 'venv/pyvenv.cfg'
    $missingPython = Join-Path $env:RUNNER_TEMP 'removed-cli-base-python'
    $brokenConfig = "home = $missingPython`ninclude-system-site-packages = false`nversion = 3.12.0`n"
    Set-Content -LiteralPath $venvConfig -Encoding ASCII -Value $brokenConfig
    & "$bundle/install.ps1" -InstallDirectory $install
    $backupsRepaired = @(Get-ChildItem -LiteralPath $install -Directory -Filter 'venv-backup-*').Count
    if ($backupsRepaired -ne ($backupsAfter + 1)) { throw 'Broken base Python did not trigger one backed-up rebuild' }
    $repairedVersion = & "$install/bin/ml.cmd" --version
    if ($LASTEXITCODE -ne 0 -or $repairedVersion -notmatch "ml $version") { throw 'Automatic repair left an unusable CLI' }
    & $installedPython -I -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
    if ($LASTEXITCODE -ne 0) { throw 'Automatic repair changed the selected environment' }
    if ($mode -eq 'offline') {
        Remove-Item Env:PIP_NO_INDEX, Env:PIP_INDEX_URL, Env:PIP_NO_CACHE_DIR
    }
}

# Install the prior version, then run the new offline installer over that environment.
$upgrade = Join-Path $env:RUNNER_TEMP 'cli-upgrade'
py -3 -m venv "$upgrade/venv"
if ($LASTEXITCODE -ne 0) { throw 'Upgrade venv failed' }
$python = "$upgrade/venv/Scripts/python.exe"
$oldWheel = @(Get-ChildItem "$env:RUNNER_TEMP/previous-wheel" -Filter '*.whl')[0].FullName
& $python -m pip install --no-index --find-links "$bundle/packages" $oldWheel
if ($LASTEXITCODE -ne 0) { throw 'Previous install failed' }
$before = & "$upgrade/venv/Scripts/ml.exe" --version
if ($before -notmatch 'ml 1\.0\.7\.1$') { throw 'Wrong previous version' }
& $python -c "from wiserec_cli.config import ConfigManager; ConfigManager().use_profile('test')"
if ($LASTEXITCODE -ne 0) { throw 'Previous CLI environment selection failed' }
$env:PIP_NO_INDEX = '1'
$env:PIP_NO_CACHE_DIR = '1'
& "$bundle/install.ps1" -InstallDirectory $upgrade
$after = & "$upgrade/venv/Scripts/ml.exe" --version
if ($LASTEXITCODE -ne 0 -or $after -notmatch "ml $version") { throw 'Upgrade failed' }

& $python -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
if ($LASTEXITCODE -ne 0) { throw 'Upgrade changed selected environment' }
