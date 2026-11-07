$ErrorActionPreference = 'Stop'
function Assert-AgentResources([string]$Python) {
    $check = @'
import hashlib, json, os
from pathlib import Path
from wiserec_cli.opencode_install import RESOURCE_ROOT
manifest = json.loads((RESOURCE_ROOT / 'manifest.json').read_text(encoding='utf-8'))
required = {'commands/ml.md', 'skills/wiserec-platform/SKILL.md'}
assert required <= set(manifest), 'Missing bundled agent resources'
assert not any('ml-lab' in key or 'wiserec-platform-detailed' in key for key in manifest)
opencode = Path(os.environ.get('OPENCODE_CONFIG_DIR') or Path.home() / '.config/opencode')
for commands, skills in ((opencode, Path.home() / '.agents'),
                         (Path.home() / '.cac', Path.home() / '.cac')):
    assert not (skills / 'skills/wiserec-platform-detailed').exists()
    assert not (commands / 'commands/ml-lab.md').exists()
    for relative, digest in manifest.items():
        target = skills if relative.startswith('skills/') else commands
        assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == digest, (target, relative)
if opencode.resolve() not in ((Path.home() / '.agents').resolve(), (Path.home() / '.cac').resolve()):
    for name in ('wiserec-platform', 'wiserec-platform-detailed'):
        assert not (opencode / 'skills' / name).exists(), 'Legacy OpenCode skill remains'
print('Skill and slash command verified in shared directory, OpenCode and codeagent')
'@
    & $Python -c $check
    if ($LASTEXITCODE -ne 0) { throw 'Agent resource verification failed' }
}

function Set-ConfigOverrideProbe([string]$Python, [string]$CurrentName = "test") {
    $probe = @'
import json, sys
from wiserec_cli.config import ConfigManager
manager = ConfigManager()
settings = json.loads(manager.path.read_text(encoding='utf-8'))
settings['current'] = sys.argv[1]
settings['auth'] = {'auto_ping': False, 'ping_interval_minutes': 15}
settings['access_control'] = {'enabled': False, 'url': 'https://old.example'}
settings['profiles'][0].update(api_endpoint='https://old.example', platform_type='mlops',
    command_policy={'deny': ['ml jupyter files upload']})
settings['local_only'] = True
manager.path.write_text(json.dumps(settings), encoding='utf-8')
'@
    & $Python -c $probe $CurrentName
    if ($LASTEXITCODE -ne 0) { throw 'Config override probe failed' }
}
function Assert-PackagedConfig([string]$Python, [string]$CurrentName = "test") {
    $check = @'
import json, sys
from wiserec_cli.config import ConfigManager
from wiserec_cli.install_config import packaged_config_text
manager = ConfigManager()
actual = json.loads(manager.path.read_text(encoding='utf-8'))
expected = json.loads(packaged_config_text())
if sys.argv[1] != "__package_default__":
    expected['current'] = sys.argv[1]
assert actual == expected, 'Installer must replace all config fields except local current'
'@
    & $Python -c $check $CurrentName
    if ($LASTEXITCODE -ne 0) { throw 'Installed config differs from package except current' }
}

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
    Assert-AgentResources $installedPython
    $modulePath = (& $installedPython -c 'import wiserec_cli; print(wiserec_cli.__file__)' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $modulePath)) { throw 'Installed CLI package was not found' }
    & $installedPython -c "from wiserec_cli.config import ConfigManager; ConfigManager().use_profile('test')"
    if ($LASTEXITCODE -ne 0) { throw 'Selecting environment before reinstall failed' }
    Set-ConfigOverrideProbe $installedPython
    Add-Content -LiteralPath $modulePath -Value '# same-version-reinstall-probe'
    & "$bundle/install.ps1" -InstallDirectory $install
    if (Select-String -LiteralPath $modulePath -Pattern 'same-version-reinstall-probe' -Quiet) {
        throw 'Same-version installation did not replace the CLI Wheel'
    }
    & $installedPython -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
    if ($LASTEXITCODE -ne 0) { throw 'Same-version reinstall changed selected environment' }
    Assert-PackagedConfig $installedPython
    Set-ConfigOverrideProbe $installedPython "product-not-in-package"
    & "$bundle/install.ps1" -InstallDirectory $install
    Assert-PackagedConfig $installedPython "__package_default__"
    Assert-AgentResources $installedPython
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
if ($before -notmatch 'ml 1\.0\.7\.10$') { throw 'Wrong previous version' }
& $python -c "from wiserec_cli.config import ConfigManager; ConfigManager().use_profile('test')"
if ($LASTEXITCODE -ne 0) { throw 'Previous CLI environment selection failed' }
Set-ConfigOverrideProbe $python
$site = (& $python -c 'import sysconfig; print(sysconfig.get_path("purelib"))').Trim()
$oldEditable = Join-Path $site '__editable__.wiserec_cli-1.0.3.8.pth'
Set-Content -LiteralPath $oldEditable -Value '# stale editable installation probe' -Encoding ASCII
$env:PIP_NO_INDEX = '1'
$env:PIP_NO_CACHE_DIR = '1'
& "$bundle/install.ps1" -InstallDirectory $upgrade
if (Test-Path -LiteralPath $oldEditable) { throw 'Stale CLI editable installation survived upgrade' }
$after = & "$upgrade/venv/Scripts/ml.exe" --version
if ($LASTEXITCODE -ne 0 -or $after -notmatch "ml $version") { throw 'Upgrade failed' }

& $python -c "from wiserec_cli.config import ConfigManager; assert ConfigManager().current_name == 'test'"
if ($LASTEXITCODE -ne 0) { throw 'Upgrade changed selected environment' }

Assert-PackagedConfig $python
Assert-AgentResources $python
