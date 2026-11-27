# Run only in a disposable Windows account. The workflow builds the input packages.
param(
    [Parameter(Mandatory = $true)][string] $Packages,
    [Parameter(Mandatory = $true)][string] $ReplacementPackages,
    [Parameter(Mandatory = $true)][string] $UpgradePackages,
    [Parameter(Mandatory = $true)][string] $Work,
    [string] $PreviousPackages
)

$ErrorActionPreference = 'Stop'

function Get-Package($Directory, $Extension) {
    $files = @(Get-ChildItem -LiteralPath $Directory -Filter "*.$Extension" -File)
    if ($files.Count -ne 1) { throw "Expected one .$Extension in $Directory" }
    return $files[0].FullName
}

function Invoke-Msi($Mode, $Package, $Operation, $Expected = 0, $Properties = '') {
    $log = Join-Path $Work "$Operation.log"
    $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -Wait -PassThru `
        -ArgumentList "$Mode `"$Package`" /qn /norestart /l*v `"$log`" $Properties"
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
    try {
        $null = $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null)
        while ($record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)) {
            try {
                $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
            } finally {
                $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($record)
            }
        }
    } finally {
        $null = $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null)
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($view)
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($database)
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($installer)
    }
}

function Get-ProductState($ProductCode) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    try {
        return $installer.GetType().InvokeMember('ProductState', 'GetProperty', $null, $installer, @($ProductCode))
    } finally {
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($installer)
    }
}

function Invoke-AutomaticUpgradeFixture($Package, $Exe, $ExpectedVersion) {
    $fixture = Join-Path $Work 'automatic-upgrade'
    New-Item -ItemType Directory -Path $fixture | Out-Null
    $download = Join-Path $fixture 'download.msi'
    Copy-Item -LiteralPath $Package -Destination $download

    $baselineVersion = (& $Exe --version) -replace '^ml ', ''
    $script = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot '../../internal/updater/upgrade.ps1')
    $powershell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell/v1.0/powershell.exe'
    $env:WISECLI_UPGRADE_EXE = $Exe
    $env:WISECLI_UPGRADE_PACKAGE = $download
    $env:WISECLI_UPGRADE_CURRENT = $baselineVersion
    $env:WISECLI_UPGRADE_MINIMUM = $baselineVersion
    $env:WISECLI_UPGRADE_RECOMMENDED = ''
    $env:WISECLI_UPGRADE_LOCK = Join-Path $Work 'test-updater.lock'
    $env:WISECLI_UPGRADE_PARENT = '2147483647'

    try {
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
        $stderr = Join-Path $Work 'updater-stderr.log'
        $stdout = Join-Path $Work 'updater-stdout.log'
        $shellArguments = @('-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-EncodedCommand')

        # The real unsigned MSI must pass verification without a hash or signer pin.
        $env:WISECLI_UPGRADE_MODE = 'verify'
        $result = Start-Process -FilePath $powershell -Wait -PassThru -ArgumentList ($shellArguments + $encoded) `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if ($result.ExitCode -ne 0) {
            throw "Unsigned MSI verification failed: $(Get-Content -LiteralPath $stderr -Raw)"
        }
        $filename = (Get-Content -LiteralPath $stdout -Raw).Trim()
        $staged = Join-Path $fixture "wiserec-cli-${ExpectedVersion}-windows-x64.msi"
        if ($filename -cne [IO.Path]::GetFileName($staged) -or
            -not (Test-Path -LiteralPath $staged -PathType Leaf) -or (Test-Path -LiteralPath $download)) {
            throw "Verified MSI was not staged under its product version: $filename"
        }

        $env:WISECLI_UPGRADE_PACKAGE = $staged
        $env:WISECLI_UPGRADE_MODE = 'install'
        $result = Start-Process -FilePath $powershell -Wait -PassThru -ArgumentList ($shellArguments + $encoded) `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        Get-Content -LiteralPath $stderr
        if ($result.ExitCode -ne 0) {
            $log = Join-Path $fixture 'install.log'
            if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 120 }
            throw "Automatic upgrade worker failed: $($result.ExitCode)"
        }
        if (Test-Path -LiteralPath $staged) { throw 'Automatic upgrade left the staged package' }
    } finally {
        foreach ($name in @('EXE', 'PACKAGE', 'CURRENT', 'MINIMUM', 'RECOMMENDED', 'LOCK', 'PARENT', 'MODE')) {
            Remove-Item -LiteralPath "Env:WISECLI_UPGRADE_$name" -ErrorAction SilentlyContinue
        }
    }
}

function New-RollbackFixture($Source, $Destination) {
    Copy-Item -LiteralPath $Source -Destination $Destination
    # Inject a deferred failure after the PATH change into the test copy only.
    if (-not ('MsiRollbackFixture' -as [type])) {
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
    }
    [MsiRollbackFixture]::Run($Destination, @(
        'INSERT INTO `CustomAction` (`Action`, `Type`, `Source`, `Target`) VALUES (''TestRollbackPath'', 1026, ''InstallerHelper'', ''test-failure'')',
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
    $logHelp = & ml train logs download --help
    if ($LASTEXITCODE -ne 0 -or ($logHelp -join ' ') -notmatch '--retry') {
        throw 'Installed CLI is missing job-level training log retry'
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
    $context = & ml context --json | ConvertFrom-Json
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
$replacement = Get-Package $ReplacementPackages 'msi'
$upgrade = Get-Package $UpgradePackages 'msi'
$portable = Join-Path $Work 'portable'
$portableReplacement = Join-Path $Work 'portable-replacement'
$portableUpgrade = Join-Path $Work 'portable-upgrade'
Expand-Archive (Get-Package $Packages 'zip') $portable
Expand-Archive (Get-Package $ReplacementPackages 'zip') $portableReplacement
Expand-Archive (Get-Package $UpgradePackages 'zip') $portableUpgrade
foreach ($payload in @($portable, $portableReplacement, $portableUpgrade)) {
    if (Get-ChildItem -LiteralPath $payload -File -Filter '*config*.json') {
        throw 'Portable package contains a standalone deployment configuration'
    }
}
$currentVersion = (Get-Content (Join-Path $portable 'release.json') -Raw | ConvertFrom-Json).version
$upgradeVersion = (Get-Content (Join-Path $portableUpgrade 'release.json') -Raw | ConvertFrom-Json).version
$versionQuery = 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductVersion'''
if ((Get-MsiValues $baseline $versionQuery) -ne $currentVersion -or
    (Get-MsiValues $replacement $versionQuery) -ne $currentVersion -or
    (Get-Content (Join-Path $portableReplacement 'release.json') -Raw | ConvertFrom-Json).version -ne $currentVersion -or
    (Get-MsiValues $upgrade $versionQuery) -ne $upgradeVersion) {
    throw 'MSI metadata and ZIP release.json must report the same version'
}
$productCodeQuery = 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductCode'''
$baselineCode = Get-MsiValues $baseline $productCodeQuery
$replacementCode = Get-MsiValues $replacement $productCodeQuery
if (-not $baselineCode -or -not $replacementCode -or $baselineCode -eq $replacementCode) {
    throw 'Two builds of the same version must have distinct ProductCodes.'
}
$exitDialogs = @{
    '-1' = 'InstallationComplete'
    '-2' = 'InstallationCancelled'
    '-3' = 'InstallationFailed'
}
$fileInUseProcessLists = 'SELECT `Dialog_` FROM `Control` WHERE `Type` = ''ListBox'' AND `Property` = ''FileInUseProcess'''
$listBoxTable = 'SELECT `Name` FROM `_Tables` WHERE `Name` = ''ListBox'''
$successVersion = 'SELECT `Text` FROM `Control` WHERE `Dialog_` = ''InstallationComplete'' AND `Control` = ''CliVersion'''
$progressQuery = 'SELECT `Dialog_` FROM `Control` WHERE `Type` = ''ProgressBar'''
$completionBitmap = 'SELECT `Control` FROM `Control` WHERE `Dialog_` = ''InstallationComplete'' AND `Type` = ''Bitmap'''
$productNameQuery = 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductName'''
foreach ($package in @($baseline, $replacement, $upgrade)) {
    $productNames = @(Get-MsiValues $package $productNameQuery)
    if ($productNames.Count -ne 1 -or $productNames[0] -cne 'WiseRec CLI') {
        throw "MSI ProductName must be exactly 'WiseRec CLI'. MSI: $package"
    }
    $progress = @(Get-MsiValues $package $progressQuery)
    $bitmaps = @(Get-MsiValues $package $completionBitmap)
    if ($progress.Count -ne 1 -or $progress[0] -ne 'Installing' -or $bitmaps.Count -ne 0) {
        throw "Expected one Installing progress bar and no completion bitmap. Progress ($($progress.Count)): [$($progress -join ', ')]; bitmaps ($($bitmaps.Count)): [$($bitmaps -join ', ')]. MSI: $package"
    }
    foreach ($sequence in $exitDialogs.Keys) {
        $query = ('SELECT `Action` FROM `InstallUISequence` WHERE `Sequence` = {0}' -f $sequence)
        if ((Get-MsiValues $package $query) -cne $exitDialogs[$sequence]) {
            throw "MSI is missing the expected exit dialog for sequence $sequence. MSI: $package"
        }
    }
    $processLists = @(Get-MsiValues $package $fileInUseProcessLists)
    if ($processLists -cnotcontains 'FilesInUse' -or $processLists -cnotcontains 'MsiRMFilesInUse' -or
        (Get-MsiValues $package $listBoxTable) -cne 'ListBox') {
        throw "MSI must include both built-in file-in-use dialog names and their process lists. MSI: $package"
    }
    $phaseQuery = 'SELECT `Description` FROM `ActionText` WHERE `Action` = '
    if ((Get-MsiValues $package ($phaseQuery + "'InstallFiles'")) -cne '正在安装 CLI…' -or
        (Get-MsiValues $package ($phaseQuery + "'InstallSkills'")) -cne '正在安装 Skill…' -or
        (Get-MsiValues $package ($phaseQuery + "'InstallShortcuts'")) -cne '正在注册 /ml 快捷命令…') {
        throw 'MSI must describe the CLI, Skill and shortcut installation phases.'
    }
    $sameVersion = 'SELECT `Text` FROM `Control` WHERE `Dialog_` = ''ConfirmSameVersionReplacement'' AND `Control` = ''Warning'''
    $approvalEvent = 'SELECT `Argument` FROM `ControlEvent` WHERE `Dialog_` = ''ConfirmSameVersionReplacement'' AND `Control_` = ''Replace'' AND `Event` = ''[WISECLI_REPLACE_SAME_VERSION]'' AND `Ordering` = 1'
    $cancelEvent = 'SELECT `Argument` FROM `ControlEvent` WHERE `Dialog_` = ''ConfirmSameVersionReplacement'' AND `Control_` = ''Cancel'' AND `Event` = ''EndDialog'''
    if ((Get-MsiValues $package $sameVersion) -notlike '*是否卸载现有安装*' -or
        (Get-MsiValues $package $approvalEvent) -ne '1' -or (Get-MsiValues $package $cancelEvent) -ne 'Exit') {
        throw 'MSI must require explicit confirmation before replacing a same-version installation.'
    }
    $actionSequence = 'SELECT `Sequence` FROM `InstallUISequence` WHERE `Action` = '
    $detect = [int](Get-MsiValues $package ($actionSequence + "'FindRelatedProducts'"))
    $confirm = [int](Get-MsiValues $package ($actionSequence + "'ConfirmSameVersionReplacement'"))
    $check = [int](Get-MsiValues $package ($actionSequence + "'LaunchConditions'"))
    if ($detect -le 0 -or $confirm -le $detect -or $check -le $confirm) {
        throw 'MSI must detect the old installation before prompting and check consent after prompting.'
    }
    $samePackageApproval = 'SELECT `Argument` FROM `ControlEvent` WHERE `Dialog_` = ''ConfirmSamePackageReinstall'' AND `Control_` = ''Reinstall'' AND `Event` = ''[WISECLI_REPLACE_SAME_VERSION]'' AND `Ordering` = 1'
    $samePackageCancel = 'SELECT `Argument` FROM `ControlEvent` WHERE `Dialog_` = ''ConfirmSamePackageReinstall'' AND `Control_` = ''Cancel'' AND `Event` = ''EndDialog'''
    $samePackageConfirm = [int](Get-MsiValues $package ($actionSequence + "'ConfirmSamePackageReinstall'"))
    $reinstallMode = [int](Get-MsiValues $package ($actionSequence + "'SetSamePackageReinstallMode'"))
    $reinstall = [int](Get-MsiValues $package ($actionSequence + "'SetSamePackageReinstall'"))
    $cost = [int](Get-MsiValues $package ($actionSequence + "'CostInitialize'"))
    if ((Get-MsiValues $package $samePackageApproval) -ne '1' -or
        (Get-MsiValues $package $samePackageCancel) -ne 'Exit' -or $samePackageConfirm -le 0 -or
        $reinstallMode -le $samePackageConfirm -or $reinstall -le $reinstallMode -or $reinstall -ge $cost) {
        throw 'MSI must confirm repeating the same package before setting the reinstall properties.'
    }
    $versionLabels = @(Get-MsiValues $package $successVersion)
    $packageVersion = Get-MsiValues $package $versionQuery
    if ($versionLabels.Count -ne 1 -or $versionLabels[0] -cne "当前安装版本：$packageVersion") {
        throw "MSI completion dialog must display the installed CLI version $packageVersion."
    }
}
if ((& (Join-Path $portable 'ml.exe') --version) -ne "ml $currentVersion") { throw 'Wrong portable version' }

$homeDir = [Environment]::GetFolderPath('UserProfile')
$agents = Join-Path $homeDir '.agents'
$cac = Join-Path $homeDir '.cac'
$openCode = Join-Path $homeDir '.config/opencode'
$installedExe = Join-Path $env:LOCALAPPDATA 'Programs/WiseRecCLIGo/ml.exe'
$goConfig = Join-Path $env:APPDATA 'ml-go-preview\config.json'
$pythonConfig = Join-Path $env:APPDATA 'ml/config.json'
$pythonCredentials = Join-Path $env:APPDATA 'ml/credentials.json'
$conflict = Join-Path $Work 'custom Python/bin'
$pythonExe = Join-Path $Work 'custom Python/venv/Scripts/ml.exe'
$otherPath = Join-Path $Work 'unrelated PATH entry'
$savePath = [Environment]::GetEnvironmentVariable('Path', 'User')
$saveOpenCode = [Environment]::GetEnvironmentVariable('OPENCODE_CONFIG_DIR', 'User')
$saveHistory = $env:ML_HISTORY
$installedMsi = $null
try {
    $env:ML_HISTORY = '0'
    New-Item -ItemType Directory -Path $conflict, $otherPath, (Split-Path $pythonExe), (Split-Path $pythonConfig), (Join-Path $openCode 'commands') -Force | Out-Null
    $launcher = Join-Path $conflict 'ml.cmd'
    Set-Content -LiteralPath $launcher -Value '@echo off' -Encoding ascii
    Set-Content -LiteralPath $pythonExe -Value 'legacy executable fixture'
    Set-Content -LiteralPath $pythonConfig -Value 'python settings'
    Set-Content -LiteralPath $pythonCredentials -Value 'legacy login fixture'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/unrelated.md') -Value 'keep'
    Set-Content -LiteralPath (Join-Path $openCode 'commands/ml-lab.md') -Value 'old entry'
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

    # A legacy environment override is ignored and preserved. Block the default shortcut only.
    $invalidOpenCode = $Work.Replace('\', '//') + '//invalid<OpenCode'
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $invalidOpenCode, 'User')
    $blockedShortcut = Join-Path $openCode 'commands/ml.md'
    New-Item -ItemType Directory -Path $blockedShortcut | Out-Null
    $log = Invoke-Msi '/i' $baseline 'install-with-shortcut-failure'
    $installedMsi = $baseline
    Refresh-Path
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CustomAction InstallShortcuts returned actual error code 1') -or
        (Select-String -LiteralPath $log -SimpleMatch 'CustomAction InstallSkills returned actual error code 1') -or
        -not (Test-Path -LiteralPath $blockedShortcut -PathType Container) -or
        (Get-Command ml -ErrorAction Stop).Source -ne $installedExe -or (ml --version) -ne "ml $currentVersion" -or
        [Environment]::GetEnvironmentVariable('OPENCODE_CONFIG_DIR', 'User') -cne $invalidOpenCode) {
        throw 'Shortcut failure must leave the CLI and Skill installed, preserving the conflict and the environment.'
    }
    foreach ($path in @((Join-Path $agents 'skills/wiserec-platform/SKILL.md'),
        (Join-Path $cac 'skills/wiserec-platform/SKILL.md'), (Join-Path $cac 'commands/ml.md'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Shortcut failure prevented installation of $path" }
    }
    Remove-Item -LiteralPath $blockedShortcut
    Invoke-Msi '/fa' $baseline 'repair-shortcut-failure' | Out-Null
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
    $portableContext = & (Join-Path $portable 'ml.exe') context --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $portableContext.'当前环境' -ne 'test' -or $portableContext.'平台地址') {
        throw 'Portable exe did not load the selected embedded environment'
    }
    Assert-Selection 'test'

    & ml env use dev
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the default test environment' }
    Assert-Selection 'dev'
    & ml env use test
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the other test environment' }
    Assert-Selection 'test'
    $configDigest = (Get-FileHash $goConfig).Hash
    Remove-Item -LiteralPath (Join-Path $openCode 'commands/ml.md')
    Invoke-Msi '/fa' $baseline 'repair' | Out-Null
    Assert-Installed $portable

    $approval = 'WISECLI_REPLACE_SAME_VERSION=1'
    $shortcut = Join-Path $openCode 'commands/ml.md'
    Set-Content -LiteralPath $installedExe -Value 'stale executable fixture' -Encoding ascii
    Remove-Item -LiteralPath $shortcut
    Invoke-Msi '/i' $baseline 'same-package-confirmed' 0 $approval | Out-Null
    if ((Get-ProductState $baselineCode) -ne 5 -or (Get-FileHash $goConfig).Hash -ne $configDigest) {
        throw 'Reinstalling the same package must preserve its registration and user configuration.'
    }
    Assert-Installed $portable

    Invoke-Msi '/i' $replacement 'same-version-unconfirmed' 1603 | Out-Null
    if ((Get-ProductState $baselineCode) -ne 5 -or (Get-ProductState $replacementCode) -ne -1) {
        throw 'Unconfirmed replacement changed the installed product.'
    }
    Assert-Installed $portable

    $sameVersionRollback = Join-Path $Work 'same-version-rollback.msi'
    New-RollbackFixture $replacement $sameVersionRollback
    $log = Invoke-Msi '/i' $sameVersionRollback 'same-version-rollback' 1603 $approval
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CustomAction TestRollbackPath returned actual error code 1') -or
        (Get-ProductState $baselineCode) -ne 5 -or (Get-ProductState $replacementCode) -ne -1) {
        throw 'Failed replacement must roll back and restore the installed product.'
    }
    Assert-Installed $portable

    Invoke-Msi '/i' $replacement 'same-version-confirmed' 0 $approval | Out-Null
    $installedMsi = $replacement
    if ((Get-ProductState $baselineCode) -ne -1 -or (Get-ProductState $replacementCode) -ne 5 -or
        (Get-FileHash $goConfig).Hash -ne $configDigest) {
        throw 'Confirmed replacement must remove the old package and preserve the user configuration.'
    }
    Assert-Installed $portableReplacement

    Set-Content -LiteralPath (Join-Path (Split-Path $installedExe) 'config.template.json') -Value 'old template'
    $customOpenCode = Join-Path $Work 'different OpenCode'
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $customOpenCode, 'User')
    Invoke-AutomaticUpgradeFixture $upgrade $installedExe $upgradeVersion
    $installedMsi = $upgrade
    Assert-Installed $portableUpgrade
    if (Test-Path -LiteralPath $customOpenCode) { throw 'Upgrade wrote to a custom OpenCode directory' }
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

    # Block one Skill file. Both shortcut locations and the other Skill copy still install.
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $null, 'User')
    $blockedSkillPath = Join-Path $agents 'skills/wiserec-platform/SKILL.md'
    New-Item -ItemType Directory -Path $blockedSkillPath -Force | Out-Null
    $log = Invoke-Msi '/i' $baseline 'install-with-skill-failure'
    $installedMsi = $baseline
    Refresh-Path
    if (-not (Select-String -LiteralPath $log -SimpleMatch 'CustomAction InstallSkills returned actual error code 1') -or
        (Select-String -LiteralPath $log -SimpleMatch 'CustomAction InstallShortcuts returned actual error code 1') -or
        -not (Test-Path -LiteralPath $blockedSkillPath -PathType Container) -or
        (Get-Command ml -ErrorAction Stop).Source -ne $installedExe -or (ml --version) -ne "ml $currentVersion") {
        throw 'Skill failure must leave the CLI and shortcuts available and preserve the conflicting directory.'
    }
    foreach ($path in @((Join-Path $openCode 'commands/ml.md'), (Join-Path $cac 'commands/ml.md'),
        (Join-Path $cac 'skills/wiserec-platform/SKILL.md'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Skill failure prevented installation of $path" }
    }
    Remove-Item -LiteralPath $blockedSkillPath
    Invoke-Msi '/fa' $baseline 'repair-skill-failure' | Out-Null
    Assert-Installed $portable
    Invoke-Msi '/x' $baseline 'uninstall-repaired-skill' | Out-Null
    $installedMsi = $null

    if ($PreviousPackages) {
        $previous = Get-Package $PreviousPackages 'msi'
        if ((Get-MsiValues $previous $versionQuery) -ne '1.1.0') { throw 'Wrong Go upgrade baseline' }
        Invoke-Msi '/i' $previous 'install-previous-go' | Out-Null
        $installedMsi = $previous
        if ((& $installedExe --version) -ne 'ml 1.1.0') { throw 'Wrong installed Go baseline' }
        Invoke-Msi '/i' $baseline 'upgrade-from-previous-go' | Out-Null
        $installedMsi = $baseline
        Assert-Installed $portable
        if ((Get-FileHash $goConfig).Hash -ne $configDigest) { throw 'Go upgrade replaced the user configuration' }
        Invoke-Msi '/x' $baseline 'uninstall-upgraded-go' | Out-Null
        $installedMsi = $null
    }
} finally {
    $env:ML_HISTORY = $saveHistory
    if ($installedMsi) { Invoke-Msi '/x' $installedMsi 'cleanup' | Out-Null }
    [Environment]::SetEnvironmentVariable('Path', $savePath, 'User')
    [Environment]::SetEnvironmentVariable('OPENCODE_CONFIG_DIR', $saveOpenCode, 'User')
}
