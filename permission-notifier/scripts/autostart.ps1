#requires -Version 5.1
[CmdletBinding()]
param([switch]$Enable, [switch]$Disable)
$ErrorActionPreference = 'Stop'
if ($Enable -eq $Disable) { throw '请选择 -Enable 或 -Disable' }
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$Name = 'PermissionNotifier-' + $Identity.User.Value
if ($Disable) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host '已关闭登录自动启动；当前运行的助手不受影响。'
    exit
}
$Target = Join-Path $env:LOCALAPPDATA 'Programs\PermissionNotifier'
$Action = New-ScheduledTaskAction -Execute (Join-Path $Target 'venv\Scripts\pythonw.exe') -Argument '-m permission_notifier.main --autostart' -WorkingDirectory $Target
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Identity.Name
$Principal = New-ScheduledTaskPrincipal -UserId $Identity.Name -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Write-Host '已启用当前用户登录后启动；正常退出不会立即重新启动。'
