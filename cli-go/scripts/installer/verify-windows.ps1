# Run only in a disposable Windows account. Both packages are built by this checkout.
param(
    [Parameter(Mandatory = $true)][string] $Packages,
    [Parameter(Mandatory = $true)][string] $UpgradePackages,
    [Parameter(Mandatory = $true)][string] $Work
)

$ErrorActionPreference = 'Stop'

function Get-Package($Directory, $Extension) {
    $files = @(Get-ChildItem -LiteralPath $Directory -Filter "*.$Extension" -File)
    if ($files.Count -ne 1) { throw "Expected one .$Extension in $Directory" }
    return $files[0].FullName
}

function Invoke-Msi($Mode, $Package, $Operation, $Expected = 0) {
    $log = Join-Path $Work "$Operation.log"
    $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -Wait -PassThru `
        -ArgumentList "$Mode `"$Package`" /qn /norestart /l*v `"$log`""
    if ($process.ExitCode -ne $Expected) {
        Get-Content -LiteralPath $log -Tail 120
        throw "$Operation exited $($process.ExitCode), expected $Expected"
    }
    return $log
}

function Get-MsiVersion($Package) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.GetType().InvokeMember('OpenDatabase', 'InvokeMethod', $null, $installer, @($Package, 0))
    $query = 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductVersion'''
    $view = $database.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $database, @($query))
    $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null)
    $record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
    $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Assert-Installed($Payload) {
    Refresh-Path
    $command = Get-Command ml -CommandType Application
    if ($command.Source -ne $installedExe) { throw "ml resolves to $($command.Source)" }
    $release = Get-Content -LiteralPath (Join-Path $Payload 'release.json') -Raw | ConvertFrom-Json
    if ((& ml --version) -ne "ml $($release.version)" -or $LASTEXITCODE -ne 0) {
        throw 'Installed ml reports the wrong version'
    }
    if ((Get-FileHash $installedExe).Hash -ne (Get-FileHash (Join-Path $Payload 'ml.exe')).Hash) {
        throw 'ZIP and MSI have different executables'
    }
    $resources = Get-Content (Join-Path $Payload 'agent/manifest.json') -Raw | ConvertFrom-Json
    foreach ($item in $resources.PSObject.Properties) {
        $roots = if ($item.Name.StartsWith('skills/')) { @($agents, $cac) } else { @($openCode, $cac) }
        foreach ($root in $roots) {
            $path = Join-Path $root $item.Name
            if ((Get-FileHash -LiteralPath $path).Hash -ne $item.Value) { throw "Incorrect agent file: $path" }
        }
    }
    $context = & ml --no-history context --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $context.'配置路径' -ne $goConfig) { throw 'Incorrect Go configuration path' }
}

New-Item -ItemType Directory -Path $Work -Force | Out-Null
$baseline = Get-Package $Packages 'msi'
$upgrade = Get-Package $UpgradePackages 'msi'
$portable = Join-Path $Work 'portable'
$portableUpgrade = Join-Path $Work 'portable-upgrade'
Expand-Archive (Get-Package $Packages 'zip') $portable
Expand-Archive (Get-Package $UpgradePackages 'zip') $portableUpgrade
$currentVersion = (Get-Content (Join-Path $portable 'release.json') -Raw | ConvertFrom-Json).version
$upgradeVersion = (Get-Content (Join-Path $portableUpgrade 'release.json') -Raw | ConvertFrom-Json).version
if ((Get-MsiVersion $baseline) -ne $currentVersion -or (Get-MsiVersion $upgrade) -ne $upgradeVersion) {
    throw 'MSI metadata and ZIP release.json must report the same version'
}
if ((& (Join-Path $portable 'ml.exe') --version) -ne "ml $currentVersion") { throw 'Wrong portable version' }

$homeDir = [Environment]::GetFolderPath('UserProfile')
$agents = Join-Path $homeDir '.agents'
$cac = Join-Path $homeDir '.cac'
$openCode = Join-Path $Work 'custom OpenCode'
$installedExe = Join-Path $env:LOCALAPPDATA 'Programs/WiseRecCLIGo/ml.exe'
$goConfig = Join-Path $env:APPDATA 'ml-go-preview\config.json'
$pythonConfig = Join-Path $env:APPDATA 'ml/config.json'
$conflict = Join-Path $Work 'custom Python'
$savePath = [Environment]::GetEnvironmentVariable('Path', 'User')
$saveOpenCode = [Environment]::GetEnvironmentVariable('OPENCODE_CONFIG_DIR', 'User')
$installedMsi = $null
try {
    New-Item -ItemType Directory -Path $conflict, (Split-Path $pythonConfig), (Join-Path $openCode 'commands') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $conflict 'ml.cmd') -Value '@echo off'
    Set-Content -LiteralPath $pythonConfig -Value 'python settings'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/unrelated.md') -Value 'keep'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/ml-lab.md') -Value 'old entry'
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $openCode, 'User')
    [Environment]::SetEnvironmentVariable('Path', "$conflict;$savePath", 'User')

    $log = Invoke-Msi '/i' $baseline 'path-conflict' 1603
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CheckForExistingMl') -or (Test-Path $installedExe)) {
        throw 'MSI did not block a conflicting ml before installation'
    }
    [Environment]::SetEnvironmentVariable('Path', $savePath, 'User')
    Invoke-Msi '/i' $baseline 'install' | Out-Null
    $installedMsi = $baseline
    Assert-Installed $portable
    if (Test-Path (Join-Path $openCode 'commands/ml-lab.md')) { throw 'Legacy shortcut remains' }

    & ml --no-history env use test
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the other test environment' }
    $configDigest = (Get-FileHash $goConfig).Hash
    Remove-Item -LiteralPath (Join-Path $openCode 'commands/ml.md')
    Invoke-Msi '/fa' $baseline 'repair' | Out-Null
    Assert-Installed $portable

    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', (Join-Path $Work 'different OpenCode'), 'User')
    Invoke-Msi '/i' $upgrade 'upgrade' | Out-Null
    $installedMsi = $upgrade
    Assert-Installed $portableUpgrade
    if ((Get-FileHash $goConfig).Hash -ne $configDigest) { throw 'Upgrade replaced the user configuration' }
    Invoke-Msi '/i' $baseline 'downgrade' 1603 | Out-Null
    Assert-Installed $portableUpgrade

    Invoke-Msi '/x' $upgrade 'uninstall' | Out-Null
    $installedMsi = $null
    Refresh-Path
    foreach ($path in @($installedExe, (Join-Path $agents 'skills/wiserec-platform/SKILL.md'),
        (Join-Path $cac 'skills/wiserec-platform/SKILL.md'), (Join-Path $cac 'commands/ml.md'),
        (Join-Path $openCode 'commands/ml.md'))) {
        if (Test-Path -LiteralPath $path) { throw "Uninstall left $path" }
    }
    if ((Get-Command ml -ErrorAction SilentlyContinue) -or
        ([Environment]::GetEnvironmentVariable('Path', 'User') -like '*WiseRecCLIGo*')) {
        throw 'Uninstall left the ml PATH entry'
    }
    if ((Get-FileHash $goConfig).Hash -ne $configDigest -or
        (Get-Content -LiteralPath $pythonConfig) -ne 'python settings' -or
        -not (Test-Path (Join-Path $openCode 'commands/unrelated.md'))) {
        throw 'Uninstall changed user configuration or unrelated resources'
    }

    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $null, 'User')
    $openCode = Join-Path $homeDir '.config/opencode'
    Invoke-Msi '/i' $baseline 'reinstall-default-opencode' | Out-Null
    $installedMsi = $baseline
    Assert-Installed $portable
    Invoke-Msi '/x' $baseline 'uninstall-default-opencode' | Out-Null
    $installedMsi = $null
} finally {
    if ($installedMsi) { Invoke-Msi '/x' $installedMsi 'cleanup' | Out-Null }
    [Environment]::SetEnvironmentVariable('Path', $savePath, 'User')
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $saveOpenCode, 'User')
}
