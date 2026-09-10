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
    & "$bundle/install.ps1" -InstallDirectory $install
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
if ($before -notmatch '0.3.42') { throw 'Wrong previous version' }
$env:PIP_NO_INDEX = '1'
$env:PIP_NO_CACHE_DIR = '1'
& "$bundle/install.ps1" -InstallDirectory $upgrade
$after = & "$upgrade/venv/Scripts/ml.exe" --version
if ($LASTEXITCODE -ne 0 -or $after -notmatch "ml $version") { throw 'Upgrade failed' }
