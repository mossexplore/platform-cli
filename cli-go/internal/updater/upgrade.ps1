$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$exe = $env:WISECLI_UPGRADE_EXE
$package = $env:WISECLI_UPGRADE_PACKAGE
$mode = $env:WISECLI_UPGRADE_MODE
$upgradeCode = '{432C0A6C-7DEF-4B10-B19F-BAEBDD4E5FE9}'

function Get-MsiProperty($Database, [string] $Name) {
    $view = $Database.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $Database,
        @("SELECT Value FROM Property WHERE Property = '$Name'"))
    try {
        $null = $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null)
        $record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
        if (-not $record) { throw "MSI 缺少 $Name。" }
        try {
            return $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
        } finally {
            $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($record)
        }
    } finally {
        $null = $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null)
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($view)
    }
}

function Get-PackageVersion([string] $Path) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    try {
        $db = $installer.GetType().InvokeMember('OpenDatabase', 'InvokeMethod', $null, $installer, @($Path, 0))
        try {
            if ((Get-MsiProperty $db 'UpgradeCode') -ne $upgradeCode) {
                throw 'MSI 产品不匹配，预期为 WiseRec CLI。'
            }
            $summary = $db.GetType().InvokeMember('SummaryInformation', 'GetProperty', $null, $db, @(0))
            try {
                $template = $summary.GetType().InvokeMember('Property', 'GetProperty', $null, $summary, @(7))
                if ($template -notmatch '^x64;') { throw '请选择 Windows x64 MSI。' }
            } finally {
                $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($summary)
            }
            return Get-MsiProperty $db 'ProductVersion'
        } finally {
            $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($db)
        }
    } finally {
        $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($installer)
    }
}

function ConvertTo-ComparableVersion([string] $Version) {
    if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$') { throw '版本格式无效。' }
    if (($Version -split '\.').Length -eq 3) { $Version += '.0' }
    return [version] $Version
}

$log = Join-Path (Split-Path -Parent $package) 'install.log'
$upgradeLock = $null
$packageLock = $null
try {
    if ($mode -eq 'install') {
        $parent = Get-Process -Id ([int] $env:WISECLI_UPGRADE_PARENT) -ErrorAction SilentlyContinue
        if ($parent -and -not $parent.WaitForExit(30000)) {
            throw 'CLI 尚未退出，请关闭占用安装目录的进程后重试。'
        }
        try {
            $upgradeLock = [IO.File]::Open($env:WISECLI_UPGRADE_LOCK, 'OpenOrCreate', 'ReadWrite', 'None')
        } catch [IO.IOException] {
            throw '已有升级在运行，请等待安装完成。'
        }
    }

    # Hold the inspected file open while Windows Installer reads it.
    $packageLock = [IO.File]::Open($package, 'Open', 'Read', 'Read')
    $targetText = Get-PackageVersion $package
    $target = ConvertTo-ComparableVersion $targetText
    $current = ConvertTo-ComparableVersion $env:WISECLI_UPGRADE_CURRENT
    if ($target -le $current) { throw '升级包版本必须高于当前版本。' }
    foreach ($required in @($env:WISECLI_UPGRADE_MINIMUM, $env:WISECLI_UPGRADE_RECOMMENDED)) {
        if ($required -and $target -lt (ConvertTo-ComparableVersion $required)) {
            throw "升级包版本 $targetText 未达到准入策略要求的 $required。"
        }
    }
    $packageName = "wiserec-cli-${targetText}-windows-x64.msi"
    if ($mode -eq 'verify') {
        # Windows requires the file to be closed before renaming it.
        $packageLock.Dispose()
        $packageLock = $null
        [IO.File]::Move($package, (Join-Path (Split-Path -Parent $package) $packageName))
        [Console]::Out.WriteLine($packageName)
        exit 0
    }
    if ([IO.Path]::GetFileName($package) -cne $packageName) {
        throw '升级包文件名与包内版本不一致。'
    }

    $currentProcesses = @(Get-Process -Name 'ml' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -ieq $exe })
    if ($currentProcesses.Count -gt 0) { throw '有其他 Go CLI 命令正在运行，请结束这些命令后重试。' }
    $before = & $exe --version
    if ($LASTEXITCODE -ne 0 -or $before -notmatch '^ml (.+)$' -or (ConvertTo-ComparableVersion $Matches[1]) -ne $current) {
        throw '当前安装版本已变化，请重新执行原命令。'
    }

    [Console]::Error.WriteLine("[信息] 正在安装 WiseRec Go CLI $targetText")
    $msiexec = Join-Path ([Environment]::SystemDirectory) 'msiexec.exe'
    $process = Start-Process -FilePath $msiexec -Wait -PassThru -ArgumentList @(
        '/i', ('"' + $package + '"'), '/qr', '/norestart', '/L*v', ('"' + $log + '"'))
    switch ($process.ExitCode) {
        0 {
            $installed = & $exe --version
            if ($LASTEXITCODE -ne 0 -or $installed -ne "ml $targetText") {
                throw 'Windows Installer 已退出，但无法确认新版本。'
            }
            [Console]::Error.WriteLine("[成功] 已升级到 $targetText，请重新执行原命令。")
        }
        3010 {
            [Console]::Error.WriteLine("[提示] 已安装 $targetText，请重启 Windows 后重新执行原命令。")
        }
        default { throw "Windows Installer 退出码为 $($process.ExitCode)。" }
    }
    Remove-Item -LiteralPath $log -ErrorAction SilentlyContinue
} catch {
    [Console]::Error.WriteLine("[错误] $($_.Exception.Message)")
    if (Test-Path -LiteralPath $log) { [Console]::Error.WriteLine("安装日志：$log") }
    exit 1
} finally {
    if ($packageLock) { $packageLock.Dispose() }
    if ($upgradeLock) { $upgradeLock.Dispose() }
    if ($mode -eq 'install') {
        Remove-Item -LiteralPath $package -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $log)) {
            Remove-Item -LiteralPath (Split-Path -Parent $package) -ErrorAction SilentlyContinue
        }
    }
}
