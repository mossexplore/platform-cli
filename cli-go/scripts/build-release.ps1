[CmdletBinding()]
param(
    [string] $OutputDirectory = (Join-Path $PSScriptRoot '../../dist/cli-go'),
    [string] $ConfigPath,
    [switch] $PortableOnly,
    [string] $Python = 'python',
    [string] $Wix = 'wix'
)

$ErrorActionPreference = 'Stop'
$module = Split-Path $PSScriptRoot
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$work = Join-Path $output ('.work-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $work 'payload'
$installer = Join-Path $PSScriptRoot 'installer'
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
    $arguments = @((Join-Path $installer 'stage.py'), $work)
    if ($ConfigPath) { $arguments += @('--config', $ConfigPath) }
    if (-not $PortableOnly) { $arguments += '--msi' }
    $metadata = & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Preparing package inputs failed.' }
    $release = $metadata | ConvertFrom-Json
    $baseName = "wiserec-cli-go-$($release.version)-windows-x64"
    $names = @("$baseName.zip")
    if (-not $PortableOnly) { $names += "$baseName.msi" }
    foreach ($name in $names) {
        if (Test-Path -LiteralPath (Join-Path $output $name)) {
            throw "Package already exists: $name. Choose a new output directory."
        }
    }

    # Validate the exact bundled template with the Go parser on the build host.
    Push-Location $module
    try {
        & go run ./cmd/check-config (Join-Path $payload 'config.template.json')
        if ($LASTEXITCODE -ne 0) { throw 'Validating the Go configuration failed.' }
    } finally {
        Pop-Location
    }

    $build = @{ OutputDirectory = $payload }
    if (-not $PortableOnly) {
        $build.PreflightPath = Join-Path $work 'path-check.exe'
    }
    & (Join-Path $PSScriptRoot 'build-windows.ps1') @build | Out-Null

    if (-not $PortableOnly) {
        & $Wix build -arch x64 (Join-Path $installer 'package.wxs') (Join-Path $work 'agent.wxs') `
            -d "Version=$($release.version)" -d "ProductCode=$($release.productCode)" `
            -d "Work=$work" -d "Payload=$payload" -o (Join-Path $work "$baseName.msi")
        if ($LASTEXITCODE -ne 0) { throw 'WiX MSI build failed.' }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($payload, (Join-Path $work "$baseName.zip"))
    foreach ($name in $names) {
        $destination = Join-Path $output $name
        [System.IO.File]::Move((Join-Path $work $name), $destination)
        $published.Add($destination)
    }
} catch {
    foreach ($path in $published) { Remove-Item -LiteralPath $path -Force }
    throw
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force
}
$published
