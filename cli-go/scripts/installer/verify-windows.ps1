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

function Get-MsiValues($Package, $Query) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.GetType().InvokeMember('OpenDatabase', 'InvokeMethod', $null, $installer, @($Package, 0))
    $view = $database.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $database, @($Query))
    $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null)
    while ($record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)) {
        $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
    }
}

function New-RollbackFixture($Source, $Destination) {
    Copy-Item -LiteralPath $Source -Destination $Destination
    # Inject a deferred failure after the PATH change into the test copy only.
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class MsiRollbackFixture
{
    [DllImport("msi.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern uint MsiOpenDatabaseW(string path, IntPtr mode, out uint database);
    [DllImport("msi.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern uint MsiDatabaseOpenViewW(uint database, string sql, out uint view);
    [DllImport("msi.dll")]
    private static extern uint MsiViewExecute(uint view, uint record);
    [DllImport("msi.dll")]
    private static extern uint MsiDatabaseCommit(uint database);
    [DllImport("msi.dll")]
    private static extern uint MsiCloseHandle(uint handle);

    public static void Run(string path, string[] queries)
    {
        uint database;
        Check(MsiOpenDatabaseW(path, new IntPtr(1), out database), "Open MSI for update");
        try
        {
            foreach (string sql in queries)
            {
                uint view;
                Check(MsiDatabaseOpenViewW(database, sql, out view), sql);
                try { Check(MsiViewExecute(view, 0), sql); }
                finally { MsiCloseHandle(view); }
            }
            Check(MsiDatabaseCommit(database), "Commit test MSI");
        }
        finally { MsiCloseHandle(database); }
    }

    private static void Check(uint error, string operation)
    {
        if (error != 0) throw new Win32Exception((int)error, operation + " failed: " + error);
    }
}
'@
    [MsiRollbackFixture]::Run($Destination, @(
        'INSERT INTO `CustomAction` (`Action`, `Type`, `Source`, `Target`) VALUES (''TestRollbackPath'', 1026, ''PathCheck'', ''test-failure'')',
        'INSERT INTO `InstallExecuteSequence` (`Action`, `Condition`, `Sequence`) VALUES (''TestRollbackPath'', ''NOT Installed'', 6550)'
    ))
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
    if (Test-Path -LiteralPath (Join-Path (Split-Path $installedExe) 'config.template.json')) {
        throw 'MSI left a standalone deployment configuration'
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

function Assert-Selection($Expected) {
    $selection = Get-Content -LiteralPath $goConfig -Raw | ConvertFrom-Json -AsHashtable
    if ($selection.Count -ne 1 -or $selection.current -ne $Expected) {
        throw "Expected the Go user configuration to contain only current=$Expected"
    }
}

New-Item -ItemType Directory -Path $Work -Force | Out-Null
$baseline = Get-Package $Packages 'msi'
$upgrade = Get-Package $UpgradePackages 'msi'
$portable = Join-Path $Work 'portable'
$portableUpgrade = Join-Path $Work 'portable-upgrade'
Expand-Archive (Get-Package $Packages 'zip') $portable
Expand-Archive (Get-Package $UpgradePackages 'zip') $portableUpgrade
foreach ($payload in @($portable, $portableUpgrade)) {
    if (Get-ChildItem -LiteralPath $payload -File -Filter '*config*.json') {
        throw 'Portable package contains a standalone deployment configuration'
    }
}
$currentVersion = (Get-Content (Join-Path $portable 'release.json') -Raw | ConvertFrom-Json).version
$upgradeVersion = (Get-Content (Join-Path $portableUpgrade 'release.json') -Raw | ConvertFrom-Json).version
$versionQuery = 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductVersion'''
if ((Get-MsiValues $baseline $versionQuery) -ne $currentVersion -or
    (Get-MsiValues $upgrade $versionQuery) -ne $upgradeVersion) {
    throw 'MSI metadata and ZIP release.json must report the same version'
}
$successDialog = 'SELECT `Action` FROM `InstallUISequence` WHERE `Action` = ''InstallationComplete'' AND `Sequence` = -1'
$progressQuery = 'SELECT `Dialog_` FROM `Control` WHERE `Type` = ''ProgressBar'''
$completionBitmap = 'SELECT `Control` FROM `Control` WHERE `Dialog_` = ''InstallationComplete'' AND `Type` = ''Bitmap'''
foreach ($package in @($baseline, $upgrade)) {
    $progress = @(Get-MsiValues $package $progressQuery)
    if ($progress.Count -ne 1 -or $progress[0] -ne 'Installing' -or (Get-MsiValues $package $completionBitmap)) {
        throw "MSI must show a single progress bar in the Installing dialog: $package"
    }
    if ((Get-MsiValues $package $successDialog) -ne 'InstallationComplete') {
        throw 'MSI must show the completion dialog only after the installation succeeds'
    }
}
if ((& (Join-Path $portable 'ml.exe') --version) -ne "ml $currentVersion") { throw 'Wrong portable version' }

$homeDir = [Environment]::GetFolderPath('UserProfile')
$agents = Join-Path $homeDir '.agents'
$cac = Join-Path $homeDir '.cac'
$openCode = Join-Path $Work 'custom OpenCode'
$installedExe = Join-Path $env:LOCALAPPDATA 'Programs/WiseRecCLIGo/ml.exe'
$goConfig = Join-Path $env:APPDATA 'ml-go-preview\config.json'
$pythonConfig = Join-Path $env:APPDATA 'ml/config.json'
$pythonCredentials = Join-Path $env:APPDATA 'ml/credentials.json'
$conflict = Join-Path $Work 'custom Python/bin'
$pythonExe = Join-Path $Work 'custom Python/venv/Scripts/ml.exe'
$otherPath = Join-Path $Work 'unrelated PATH entry'
$savePath = [Environment]::GetEnvironmentVariable('Path', 'User')
$saveOpenCode = [Environment]::GetEnvironmentVariable('OPENCODE_CONFIG_DIR', 'User')
$installedMsi = $null
try {
    New-Item -ItemType Directory -Path $conflict, $otherPath, (Split-Path $pythonExe), (Split-Path $pythonConfig), (Join-Path $openCode 'commands') -Force | Out-Null
    $launcher = Join-Path $conflict 'ml.cmd'
    Set-Content -LiteralPath $launcher -Value '@echo off' -Encoding ascii
    Set-Content -LiteralPath $pythonExe -Value 'legacy executable fixture'
    Set-Content -LiteralPath $pythonConfig -Value 'python settings'
    Set-Content -LiteralPath $pythonCredentials -Value 'legacy login fixture'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/unrelated.md') -Value 'keep'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/ml-lab.md') -Value 'old entry'
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $openCode, 'User')
    $pathWithConflict = "$otherPath;$conflict;$savePath"
    [Environment]::SetEnvironmentVariable('Path', $pathWithConflict, 'User')

    $log = Invoke-Msi '/i' $baseline 'unknown-path-conflict' 1603
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CheckForExistingMl') -or
        ([Environment]::GetEnvironmentVariable('Path', 'User') -ne $pathWithConflict)) {
        throw 'MSI did not preserve an unrelated PATH entry'
    }
    Set-Content -LiteralPath $launcher -Value @('@echo off', '"%~dp0..\venv\Scripts\ml.exe" %*') -Encoding ascii

    $rollback = Join-Path $Work 'rollback-test.msi'
    New-RollbackFixture $baseline $rollback
    $log = Invoke-Msi '/i' $rollback 'path-rollback' 1603
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CustomAction TestRollbackPath returned actual error code 1') -or
        (Test-Path $installedExe) -or ([Environment]::GetEnvironmentVariable('Path', 'User') -ne $pathWithConflict)) {
        throw 'MSI did not restore the previous PATH on rollback'
    }

    $log = Invoke-Msi '/i' $baseline 'install-with-legacy-path'
    $installedMsi = $baseline
    if (Select-String -LiteralPath $log -SimpleMatch 'Doing action: InstallationComplete') {
        throw 'Silent MSI ran the interactive success notification'
    }
    Assert-Installed $portable
    Assert-Selection 'dev'
    $entries = [Environment]::GetEnvironmentVariable('Path', 'User') -split ';'
    if ($entries -contains $conflict -or $entries -notcontains $otherPath -or -not (Test-Path -LiteralPath $launcher) -or
        (Get-Content -LiteralPath $pythonExe) -ne 'legacy executable fixture' -or
        (Get-Content -LiteralPath $pythonConfig) -ne 'python settings' -or
        (Get-Content -LiteralPath $pythonCredentials) -ne 'legacy login fixture') {
        throw 'MSI did not remove exactly the old launcher entry while preserving its files'
    }
    if (Test-Path (Join-Path $openCode 'commands/ml-lab.md')) { throw 'Legacy shortcut remains' }

    Set-Content -LiteralPath $goConfig -Value '{"current":"test","profiles":[],"access_control":{"enable":false}}'
    $portableContext = & (Join-Path $portable 'ml.exe') --no-history context --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $portableContext.'当前环境' -ne 'test' -or $portableContext.'平台地址') {
        throw 'Portable exe did not load the selected embedded environment'
    }
    Assert-Selection 'test'

    & ml --no-history env use dev
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the default test environment' }
    Assert-Selection 'dev'
    & ml --no-history env use test
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the other test environment' }
    Assert-Selection 'test'
    $configDigest = (Get-FileHash $goConfig).Hash
    Remove-Item -LiteralPath (Join-Path $openCode 'commands/ml.md')
    Invoke-Msi '/fa' $baseline 'repair' | Out-Null
    Assert-Installed $portable

    Set-Content -LiteralPath (Join-Path (Split-Path $installedExe) 'config.template.json') -Value 'old template'
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
