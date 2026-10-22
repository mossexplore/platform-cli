#requires -Version 5.1
[CmdletBinding()]
param([switch]$AutoStart, [string]$IndexUrl = '')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $env:LOCALAPPDATA 'Programs\PermissionNotifier'
$Data = Join-Path $env:LOCALAPPDATA 'PermissionNotifier'
if (Get-Process python,pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Target\*" }) {
    throw '请先通过托盘退出权限通知助手，再执行安装或升级。'
}
New-Item -ItemType Directory -Force -Path $Target,$Data | Out-Null
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $Data /inheritance:r /grant:r "${Identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '无法设置本地数据目录权限' }
& py.exe -3.12 -m venv (Join-Path $Target 'venv')
if ($LASTEXITCODE -ne 0) { throw '需要安装 Python 3.12' }
$Python = Join-Path $Target 'venv\Scripts\python.exe'
$PipArgs = @('-m','pip','install','--upgrade',$Root)
if ($IndexUrl) { $PipArgs += @('--index-url',$IndexUrl) }
& $Python @PipArgs
if ($LASTEXITCODE -ne 0) { throw '助手安装失败' }
$PythonW = Join-Path $Target 'venv\Scripts\pythonw.exe'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) '权限通知助手.lnk'))
$Shortcut.TargetPath = $PythonW
$Shortcut.Arguments = '-m permission_notifier.main'
$Shortcut.WorkingDirectory = $Target
$Shortcut.Save()
Copy-Item (Join-Path $PSScriptRoot 'autostart.ps1') $Target -Force
Copy-Item (Join-Path $PSScriptRoot 'uninstall.ps1') $Target -Force
if ($AutoStart) { & (Join-Path $Target 'autostart.ps1') -Enable }
Write-Host '安装完成。使用桌面“权限通知助手”启动；配置保存在个人用户目录，不影响业务 CLI。'
