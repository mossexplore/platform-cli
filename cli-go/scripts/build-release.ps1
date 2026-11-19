[CmdletBinding()]
param(
    [string] $OutputDirectory,
    [string] $ConfigPath,
    [switch] $NewOutputDirectory,
    [switch] $PortableOnly,
    [string] $Python = 'python',
    [string] $Wix = 'wix'
)

$ErrorActionPreference = 'Stop'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'dist'
}
if ($NewOutputDirectory) {
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $OutputDirectory = Join-Path $OutputDirectory "$(Get-Date -Format yyyyMMdd-HHmmss)-$suffix"
}
$output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$work = Join-Path $output ('.work-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $work 'payload'
$installer = Join-Path $PSScriptRoot 'installer'
Write-Verbose "Checking build tools and preparing output directory: $output"
Get-Command go, $Python -ErrorAction Stop | Out-Null
if (-not $PortableOnly) {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Building the MSI requires Windows. Use -PortableOnly for the ZIP on this host.'
    }
    Get-Command $Wix -ErrorAction Stop | Out-Null
}

New-Item -ItemType Directory -Path $work -Force | Out-Null
$published = [System.Collections.Generic.List[string]]::new()
try {
    Write-Verbose 'Preparing the Agent Skill files and package metadata'
    $arguments = @((Join-Path $installer 'stage.py'), $work)
    if (-not $PortableOnly) { $arguments += '--msi' }
    $metadata = & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Preparing package inputs failed.' }
    $release = $metadata | ConvertFrom-Json
    Write-Verbose "Building WiseRec CLI $($release.version) for Windows x64"
    $baseName = "wiserec-cli-$($release.version)-windows-x64"
    $names = @("$baseName.zip")
    if (-not $PortableOnly) { $names += "$baseName.msi" }
    foreach ($name in $names) {
        if (Test-Path -LiteralPath (Join-Path $output $name)) {
            throw "Package already exists: $name. Choose a new output directory."
        }
    }

    $build = @{ OutputDirectory = $payload; ConfigPath = $ConfigPath; Verbose = ($VerbosePreference -eq 'Continue') }
    if (-not $PortableOnly) {
        $build.PreflightPath = Join-Path $work 'msi-helper.exe'
        $build.AgentArchive = Join-Path $work 'agent-resources.zip'
    }
    & (Join-Path $PSScriptRoot 'build-windows.ps1') @build | ForEach-Object { Write-Verbose "$_" }

    if (-not $PortableOnly) {
        Write-Verbose "Building $baseName.msi with WiX"
        & $Wix build -arch x64 (Join-Path $installer 'package.wxs') `
            -d "Version=$($release.version)" `
            -d "Work=$work" -d "Payload=$payload" -o (Join-Path $work "$baseName.msi")
        if ($LASTEXITCODE -ne 0) { throw 'WiX MSI build failed.' }
    }
    Write-Verbose "Compressing $baseName.zip"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($payload, (Join-Path $work "$baseName.zip"))
    if (-not $PortableOnly) {
        $msiStream = [System.IO.File]::OpenRead((Join-Path $work "$baseName.msi"))
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $msiHash = [BitConverter]::ToString($sha256.ComputeHash($msiStream)).Replace('-', '').ToLowerInvariant()
        } finally {
            $sha256.Dispose()
            $msiStream.Dispose()
        }
    }
    foreach ($name in $names) {
        $destination = Join-Path $output $name
        [System.IO.File]::Move((Join-Path $work $name), $destination)
        $published.Add($destination)
        Write-Verbose "Package saved: $destination"
    }
    if (-not $PortableOnly) {
        [Console]::WriteLine("MSI SHA-256: $msiHash")
    }
} catch {
    foreach ($path in $published) { Remove-Item -LiteralPath $path -Force }
    throw
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force
}
$published
