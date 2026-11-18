param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,
    [string] $PreflightPath
)

$ErrorActionPreference = 'Stop'
$moduleDirectory = Split-Path $PSScriptRoot
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$output = Join-Path $outputRoot 'ml.exe'
if (Test-Path -LiteralPath $output) {
    throw 'Choose a new output directory to avoid replacing an existing ml.exe.'
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$environment = @{ GOOS = 'windows'; GOARCH = 'amd64'; CGO_ENABLED = '0' }
$previous = @{}
foreach ($name in $environment.Keys) {
    $previous[$name] = [System.Environment]::GetEnvironmentVariable($name)
    [System.Environment]::SetEnvironmentVariable($name, $environment[$name])
}
Push-Location $moduleDirectory
try {
    & go build -trimpath -o $output ./cmd/ml
    if ($LASTEXITCODE -ne 0) {
        throw "Go build failed with exit code $LASTEXITCODE."
    }
    if ($PreflightPath) {
        & go build -trimpath -ldflags '-s -w -H=windowsgui' -o $PreflightPath ./cmd/msi-preflight
        if ($LASTEXITCODE -ne 0) { throw 'Building the MSI preflight failed.' }
    }
} finally {
    Pop-Location
    foreach ($name in $previous.Keys) {
        [System.Environment]::SetEnvironmentVariable($name, $previous[$name])
    }
}
Write-Output $output
