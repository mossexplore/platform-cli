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
if ($before -notmatch 'ml 1\.0\.5\.7$') { throw 'Wrong previous version' }
& $python -c "from wiserec_cli.config import ConfigManager; ConfigManager().use_profile('test')"
if ($LASTEXITCODE -ne 0) { throw 'Previous CLI environment selection failed' }
$env:PIP_NO_INDEX = '1'
$env:PIP_NO_CACHE_DIR = '1'
& "$bundle/install.ps1" -InstallDirectory $upgrade
$after = & "$upgrade/venv/Scripts/ml.exe" --version
if ($LASTEXITCODE -ne 0 -or $after -notmatch "ml $version") { throw 'Upgrade failed' }

& $python -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
if ($LASTEXITCODE -ne 0) { throw 'Upgrade changed selected environment' }
