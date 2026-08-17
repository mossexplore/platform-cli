#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$InstallDirectory = "",
    [string]$IndexUrl = "",
    [string]$Cert = "",
    [switch]$Force,
    [switch]$SkipEdgeCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ScriptDirectory)) {
    throw "Unable to determine the directory containing install.ps1."
}

function Find-Python {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        return @{ Command = "py.exe"; Prefix = @("-3") }
    }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        return @{ Command = "python.exe"; Prefix = @() }
    }
    throw "Python was not found. Install Python 3.9 or newer from https://www.python.org/downloads/windows/."
}

function Assert-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required PowerShell command is not available: $Name"
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $($LASTEXITCODE): $Command"
    }
}

function Test-ReleaseChecksums {
    param([Parameter(Mandatory = $true)][string]$BundleDirectory)

    $ChecksumPath = Join-Path $BundleDirectory "CHECKSUMS.sha256"
    if (-not (Test-Path -LiteralPath $ChecksumPath)) {
        Write-Warning "CHECKSUMS.sha256 was not found; package integrity verification was skipped."
        return
    }

    foreach ($Line in Get-Content -LiteralPath $ChecksumPath) {
        if ([string]::IsNullOrWhiteSpace($Line)) {
            continue
        }
        if ($Line -notmatch '^([0-9a-fA-F]{64})\s{2}(.+)$') {
            throw "Invalid checksum line: $Line"
        }
        $ExpectedHash = $Matches[1].ToLowerInvariant()
        $RelativePath = $Matches[2].Replace("/", "\")
        $TargetPath = Join-Path $BundleDirectory $RelativePath
        if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
            throw "Release file is missing: $RelativePath"
        }
        $ActualHash = (Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            throw "Checksum verification failed: $RelativePath"
        }
    }
}

function Find-Edge {
    $Candidates = @()
    foreach ($Root in @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        $env:LOCALAPPDATA
    )) {
        if ($Root) {
            $Candidates += Join-Path $Root "Microsoft\Edge\Application\msedge.exe"
        }
    }
    return $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}

function Add-ToUserPath {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $NormalizedDirectory = $Directory.TrimEnd("\")
    $CurrentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $Entries = @(
        $CurrentUserPath -split ";" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim().TrimEnd("\") }
    )
    if ($Entries -notcontains $NormalizedDirectory) {
        $NewUserPath = (@($Entries) + $NormalizedDirectory) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
        return $true
    }
    return $false
}

if ($env:OS -ne "Windows_NT") {
    throw "This installer supports Windows only."
}
if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is not available for the current Windows user."
}
if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:LOCALAPPDATA "Programs\WiseMLOpsCLI"
}

foreach ($RequiredCommand in @(
    "ConvertFrom-Json",
    "Get-FileHash"
)) {
    Assert-RequiredCommand -Name $RequiredCommand
}

$BundleDirectory = $ScriptDirectory
Write-Host "[1/7] Verifying release package..." -ForegroundColor Cyan
Test-ReleaseChecksums -BundleDirectory $BundleDirectory

$Wheels = @(Get-ChildItem -LiteralPath $BundleDirectory -Filter "wisemlops_cli-*.whl" -File)
if ($Wheels.Count -ne 1) {
    throw "Expected exactly one wisemlops-cli Wheel next to install.ps1, but found $($Wheels.Count)."
}
$WheelPath = $Wheels[0].FullName

Write-Host "[2/7] Checking Python..." -ForegroundColor Cyan
$Python = Find-Python
$PythonCommand = $Python.Command
$PythonPrefix = @($Python.Prefix)
$PythonArguments = $PythonPrefix + @(
    "-c",
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
)
$PythonVersionText = (& $PythonCommand @PythonArguments | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the Python version."
}
$PythonVersion = [Version]$PythonVersionText
if ($PythonVersion -lt [Version]"3.9") {
    throw "Python 3.9 or newer is required. Current version: $PythonVersionText"
}
$ArchitectureArguments = $PythonPrefix + @(
    "-c",
    "import platform, struct; m=platform.machine().lower(); b=struct.calcsize('P')*8; print('arm64' if b == 64 and m in ('arm64', 'aarch64') else ('x64' if b == 64 else 'x86'))"
)
$PythonArchitecture = (& $PythonCommand @ArchitectureArguments | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0 -or $PythonArchitecture -notin @("x86", "x64", "arm64")) {
    throw "Unable to determine the Python interpreter architecture."
}
Write-Host "  Python $PythonVersionText ($PythonArchitecture)"

$ReleaseMetadataPath = Join-Path $BundleDirectory "release.json"
$ReleaseMetadata = $null
if (Test-Path -LiteralPath $ReleaseMetadataPath -PathType Leaf) {
    $ReleaseMetadata = Get-Content -LiteralPath $ReleaseMetadataPath -Raw | ConvertFrom-Json
    if ($ReleaseMetadata.mode -eq "offline") {
        $RequiredMajor = [int]$ReleaseMetadata.python_major
        $RequiredMinor = [int]$ReleaseMetadata.python_minor
        if (
            $PythonVersion.Major -ne $RequiredMajor -or
            $PythonVersion.Minor -ne $RequiredMinor
        ) {
            throw (
                "This offline package requires Python $RequiredMajor.$RequiredMinor.x, " +
                "but the current Python is $PythonVersionText. Use a matching offline " +
                "package or an online release package."
            )
        }
        $RequiredArchitecture = [string]$ReleaseMetadata.architecture
        if ($PythonArchitecture -ne $RequiredArchitecture) {
            throw (
                "This offline package requires Python architecture " +
                "$RequiredArchitecture, but the current Python architecture is " +
                "$PythonArchitecture. Use a matching offline package or an online " +
                "release package."
            )
        }
    }
}

$EffectiveIndexUrl = ""
$IndexSource = "pip configuration/default"
if (-not [string]::IsNullOrWhiteSpace($IndexUrl)) {
    $IndexUri = $null
    if (-not [Uri]::TryCreate($IndexUrl, [UriKind]::Absolute, [ref]$IndexUri)) {
        throw "IndexUrl must be an absolute URL."
    }
    if (-not [string]::IsNullOrWhiteSpace($IndexUri.UserInfo)) {
        throw "IndexUrl must not contain credentials. Use PIP_INDEX_URL for authenticated sources."
    }
    $EffectiveIndexUrl = $IndexUrl
    $IndexSource = $IndexUrl
} elseif (-not [string]::IsNullOrWhiteSpace($env:PIP_INDEX_URL)) {
    # Let pip consume the environment variable directly so credentials are not
    # copied into the command line or printed by this installer.
    $IndexSource = "PIP_INDEX_URL environment variable"
} elseif (
    $null -ne $ReleaseMetadata -and
    $null -ne $ReleaseMetadata.PSObject.Properties["index_url"]
) {
    $EffectiveIndexUrl = [string]$ReleaseMetadata.index_url
    $IndexSource = $EffectiveIndexUrl
}

Write-Host "[3/7] Checking Microsoft Edge..." -ForegroundColor Cyan
$EdgePath = Find-Edge
if (-not $EdgePath -and -not $SkipEdgeCheck) {
    throw "Microsoft Edge was not found. Install Edge or rerun with -SkipEdgeCheck if Edge is managed in a non-standard location."
}
if ($EdgePath) {
    Write-Host "  Edge: $EdgePath"
} else {
    Write-Warning "Edge check was skipped."
}

$ResolvedInstallDirectory = [System.IO.Path]::GetFullPath($InstallDirectory)
$VirtualEnvironment = Join-Path $ResolvedInstallDirectory "venv"
$BinDirectory = Join-Path $ResolvedInstallDirectory "bin"
$VirtualEnvironmentPython = Join-Path $VirtualEnvironment "Scripts\python.exe"
$VirtualEnvironmentMl = Join-Path $VirtualEnvironment "Scripts\ml.exe"

Write-Host "[4/7] Preparing isolated environment..." -ForegroundColor Cyan
if ($Force -and (Test-Path -LiteralPath $VirtualEnvironment)) {
    Remove-Item -LiteralPath $VirtualEnvironment -Recurse -Force
}
New-Item -ItemType Directory -Path $ResolvedInstallDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $VirtualEnvironmentPython)) {
    $VenvArguments = $PythonPrefix + @("-m", "venv", $VirtualEnvironment)
    Invoke-Checked -Command $PythonCommand -Arguments $VenvArguments
}

Write-Host "[5/7] Installing wisemlops-cli..." -ForegroundColor Cyan
$PackagesDirectory = Join-Path $BundleDirectory "packages"
if (Test-Path -LiteralPath $PackagesDirectory -PathType Container) {
    Invoke-Checked -Command $VirtualEnvironmentPython -Arguments @(
        "-m", "pip", "install",
        "--no-index",
        "--find-links", $PackagesDirectory,
        "--upgrade",
        "--force-reinstall",
        $WheelPath
    )
} else {
    $InstallArguments = @(
        "-m", "pip", "install",
        "--upgrade",
        "--force-reinstall"
    )
    if (-not [string]::IsNullOrWhiteSpace($EffectiveIndexUrl)) {
        $InstallArguments += @("--index-url", $EffectiveIndexUrl)
    }
    if (-not [string]::IsNullOrWhiteSpace($Cert)) {
        $ResolvedCert = [System.IO.Path]::GetFullPath($Cert)
        if (-not (Test-Path -LiteralPath $ResolvedCert -PathType Leaf)) {
            throw "The pip certificate file does not exist: $ResolvedCert"
        }
        $InstallArguments += @("--cert", $ResolvedCert)
    }
    $InstallArguments += $WheelPath
    Write-Host "  Python package index: $IndexSource"
    Invoke-Checked -Command $VirtualEnvironmentPython -Arguments $InstallArguments
}

Write-Host "[6/7] Registering the ml command..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $BinDirectory -Force | Out-Null
$LauncherPath = Join-Path $BinDirectory "ml.cmd"
$Launcher = @'
@echo off
"%~dp0..\venv\Scripts\ml.exe" %*
'@
Set-Content -LiteralPath $LauncherPath -Value $Launcher -Encoding ASCII
$PathChanged = Add-ToUserPath -Directory $BinDirectory

Write-Host "[7/7] Verifying installation..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $VirtualEnvironmentMl)) {
    throw "ml.exe was not created in the isolated environment."
}
Invoke-Checked -Command $VirtualEnvironmentMl -Arguments @("--version")

Write-Host ""
Write-Host "WiseMLOps CLI installation completed." -ForegroundColor Green
Write-Host "  Install directory: $ResolvedInstallDirectory"
Write-Host "  Command launcher:  $LauncherPath"
if ($PathChanged) {
    Write-Host ""
    Write-Host "Open a new CMD or PowerShell window before running ml." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "  ml env show"
Write-Host "  ml login"
Write-Host ""
Write-Host "Optional PowerShell Tab completion:"
Write-Host "  ml --install-completion powershell"
