#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [string]$InstallDirectory = "",
    [string]$IndexUrl = "",
    [switch]$Force,
    [switch]$SkipEdgeCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This script supports Windows only."
}
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildScript = Join-Path $ScriptDirectory "windows\build-release.ps1"
if (-not (Test-Path -LiteralPath $BuildScript -PathType Leaf)) {
    throw "Build script not found: $BuildScript"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $ScriptDirectory "..\release\local-builds"
}
# Always use a new directory, including for repeated builds of the same version.
$RunDirectory = Join-Path ([System.IO.Path]::GetFullPath($OutputDirectory)) (
    "build-" + [Guid]::NewGuid().ToString("N")
)
$BuildArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BuildScript,
    "-Online", "-OutputDirectory", $RunDirectory
)
if (-not [string]::IsNullOrWhiteSpace($IndexUrl)) {
    $BuildArguments += @("-IndexUrl", $IndexUrl)
}

Write-Host "[1/2] Building the current local source..." -ForegroundColor Cyan
& powershell.exe @BuildArguments
if ($LASTEXITCODE -ne 0) {
    throw "Build failed. Installation was not started."
}
$Bundles = @(Get-ChildItem -LiteralPath $RunDirectory -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName "install.ps1") -PathType Leaf
})
if ($Bundles.Count -ne 1) {
    throw "Expected exactly one newly built installation bundle, found $($Bundles.Count)."
}
$InstallScript = Join-Path $Bundles[0].FullName "install.ps1"
$InstallArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $InstallScript)
if (-not [string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallArguments += @("-InstallDirectory", $InstallDirectory)
}
if (-not [string]::IsNullOrWhiteSpace($IndexUrl)) {
    $InstallArguments += @("-IndexUrl", $IndexUrl)
}
if ($Force) { $InstallArguments += "-Force" }
if ($SkipEdgeCheck) { $InstallArguments += "-SkipEdgeCheck" }

Write-Host "[2/2] Installing the newly built CLI..." -ForegroundColor Cyan
& powershell.exe @InstallArguments
if ($LASTEXITCODE -ne 0) {
    throw "Installation failed. The build remains available at $RunDirectory"
}
Write-Host ""
Write-Host "Build and CLI installation completed." -ForegroundColor Green
Write-Host "Build output: $RunDirectory"
Write-Host "See the installer output for the CLI version and separate OpenCode resource result."
Write-Host "Reopen your terminal before using ml through PATH."
