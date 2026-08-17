#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [switch]$Online,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ScriptDirectory)) {
    throw "Unable to determine the directory containing build-release.ps1."
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $ScriptDirectory "..\..\release"
}

function Find-Python {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        return @{ Command = "py.exe"; Prefix = @("-3") }
    }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        return @{ Command = "python.exe"; Prefix = @() }
    }
    throw "Python was not found. Install Python 3.9 or newer first."
}

function Assert-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required PowerShell command is not available: $Name"
    }
}

function Invoke-CheckedPython {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $Command = $script:PythonCommand
    $Prefix = @($script:PythonPrefix)
    & $Command @Prefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $($LASTEXITCODE)."
    }
}

foreach ($RequiredCommand in @(
    "Compress-Archive",
    "ConvertTo-Json",
    "Get-FileHash"
)) {
    Assert-RequiredCommand -Name $RequiredCommand
}

$RepositoryRoot = (Resolve-Path (Join-Path $ScriptDirectory "..\..")).Path
$PyProjectPath = Join-Path $RepositoryRoot "pyproject.toml"
$VersionMatch = Select-String -Path $PyProjectPath -Pattern '^version\s*=\s*"([^"]+)"$'
if (-not $VersionMatch -or $VersionMatch.Matches.Count -ne 1) {
    throw "Could not determine a unique project version from pyproject.toml."
}
$Version = $VersionMatch.Matches[0].Groups[1].Value

$Python = Find-Python
$PythonCommand = $Python.Command
$PythonPrefix = @($Python.Prefix)
$script:PythonCommand = $PythonCommand
$script:PythonPrefix = $PythonPrefix
$PythonVersionArguments = $PythonPrefix + @(
    "-c",
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
)
$PythonVersionText = (& $PythonCommand @PythonVersionArguments | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the Python version."
}
$PythonVersion = [Version]$PythonVersionText
if ($PythonVersion -lt [Version]"3.9") {
    throw "Python 3.9 or newer is required. Current version: $PythonVersionText"
}
$PythonTag = "py$($PythonVersion.Major)$($PythonVersion.Minor)"

$ArchitectureArguments = $PythonPrefix + @(
    "-c",
    "import platform, struct; m=platform.machine().lower(); b=struct.calcsize('P')*8; print('arm64' if b == 64 and m in ('arm64', 'aarch64') else ('x64' if b == 64 else 'x86'))"
)
$Architecture = (& $PythonCommand @ArchitectureArguments | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0 -or $Architecture -notin @("x86", "x64", "arm64")) {
    throw "Unable to determine the Python interpreter architecture."
}
$PackageMode = if ($Online) { "online" } else { "offline" }
$BundleName = "wisemlops-cli-$Version-windows-$Architecture-$PythonTag-$PackageMode"
$ResolvedOutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$BundleDirectory = Join-Path $ResolvedOutputDirectory $BundleName
$ArchivePath = Join-Path $ResolvedOutputDirectory "$BundleName.zip"

if (Test-Path -LiteralPath $BundleDirectory) {
    if (-not $Force) {
        throw "Release directory already exists: $BundleDirectory. Use -Force to replace it."
    }
    Remove-Item -LiteralPath $BundleDirectory -Recurse -Force
}
if (Test-Path -LiteralPath $ArchivePath) {
    if (-not $Force) {
        throw "Release archive already exists: $ArchivePath. Use -Force to replace it."
    }
    Remove-Item -LiteralPath $ArchivePath -Force
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "wisemlops-cli-release-" + [Guid]::NewGuid().ToString("N")
)
$WheelDirectory = Join-Path $TemporaryRoot "wheel"

try {
    New-Item -ItemType Directory -Path $WheelDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $BundleDirectory -Force | Out-Null

    Write-Host "[1/5] Preparing Python build tools..." -ForegroundColor Cyan
    Invoke-CheckedPython -Arguments @("-m", "pip", "install", "--upgrade", "build")

    Write-Host "[2/5] Building wisemlops-cli $Version..." -ForegroundColor Cyan
    Push-Location $RepositoryRoot
    try {
        Invoke-CheckedPython -Arguments @(
            "-m", "build", "--wheel", "--outdir", $WheelDirectory
        )
    } finally {
        Pop-Location
    }

    $Wheels = @(Get-ChildItem -LiteralPath $WheelDirectory -Filter "*.whl" -File)
    if ($Wheels.Count -ne 1) {
        throw "Expected exactly one Wheel, but found $($Wheels.Count)."
    }
    $WheelPath = Join-Path $BundleDirectory $Wheels[0].Name
    Copy-Item -LiteralPath $Wheels[0].FullName -Destination $WheelPath

    Write-Host "[3/5] Copying installer files..." -ForegroundColor Cyan
    foreach ($FileName in @("install.cmd", "install.ps1", "INSTALL.md")) {
        Copy-Item -LiteralPath (Join-Path $ScriptDirectory $FileName) `
            -Destination (Join-Path $BundleDirectory $FileName)
    }
    $ReleaseMetadata = [ordered]@{
        package = "wisemlops-cli"
        version = $Version
        mode = $PackageMode
        platform = "windows"
        architecture = $Architecture
        python_major = $PythonVersion.Major
        python_minor = $PythonVersion.Minor
        python_version = $PythonVersionText
    }
    $ReleaseMetadata | ConvertTo-Json | Set-Content `
        -LiteralPath (Join-Path $BundleDirectory "release.json") `
        -Encoding UTF8

    if (-not $Online) {
        Write-Host "[4/5] Downloading offline dependencies..." -ForegroundColor Cyan
        $PackagesDirectory = Join-Path $BundleDirectory "packages"
        New-Item -ItemType Directory -Path $PackagesDirectory -Force | Out-Null
        Invoke-CheckedPython -Arguments @(
            "-m", "pip", "download",
            "--only-binary=:all:",
            "--dest", $PackagesDirectory,
            $WheelPath
        )
    } else {
        Write-Host "[4/5] Online package selected; dependencies will be downloaded during installation." -ForegroundColor Yellow
    }

    Write-Host "[5/5] Writing checksums and ZIP archive..." -ForegroundColor Cyan
    $ChecksumPath = Join-Path $BundleDirectory "CHECKSUMS.sha256"
    $ChecksumLines = foreach ($File in Get-ChildItem -LiteralPath $BundleDirectory -File -Recurse | Sort-Object FullName) {
        if ($File.FullName -eq $ChecksumPath) {
            continue
        }
        $RelativePath = $File.FullName.Substring($BundleDirectory.Length).TrimStart([char[]]"\/")
        $PortablePath = $RelativePath.Replace("\", "/")
        $Hash = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$Hash  $PortablePath"
    }
    Set-Content -LiteralPath $ChecksumPath -Value $ChecksumLines -Encoding ASCII

    Compress-Archive -Path $BundleDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal

    Write-Host ""
    Write-Host "Release package created:" -ForegroundColor Green
    Write-Host "  Directory: $BundleDirectory"
    Write-Host "  ZIP:       $ArchivePath"
    Write-Host "  Mode:      $PackageMode"
    Write-Host "  Version:   $Version"
    Write-Host "  Python:    $PythonVersionText"
    Write-Host "  Arch:      $Architecture"
} finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}
