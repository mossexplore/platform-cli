#requires -Version 5.1
[CmdletBinding()]
param([switch]$DeleteData)
$ErrorActionPreference = 'Stop'
$Target = Join-Path $env:LOCALAPPDATA 'Programs\PermissionNotifier'
if (Get-Process python,pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Target\*" }) {
    throw '请先通过托盘退出助手。'
}
& (Join-Path $Target 'autostart.ps1') -Disable
$Shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) '权限通知助手.lnk'
Remove-Item $Shortcut -ErrorAction SilentlyContinue
if ($DeleteData) {
    $Answer = Read-Host '删除配置、凭据和未完成任务可能导致无法核对消息；输入 DELETE 确认'
    if ($Answer -ne 'DELETE') { throw '已取消删除数据' }
    Remove-Item (Join-Path $env:LOCALAPPDATA 'PermissionNotifier') -Recurse -Force
}
Remove-Item $Target -Recurse -Force
Write-Host '助手已卸载。未指定并确认 DeleteData 时，个人 JSON 和日志保留。'
