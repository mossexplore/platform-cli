param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,
    [string] $PreflightPath,
    [string] $ConfigPath
)

$ErrorActionPreference = 'Stop'
$moduleDirectory = Split-Path $PSScriptRoot
$repository = Split-Path $moduleDirectory
$outputRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$output = Join-Path $outputRoot 'ml.exe'
if (Test-Path -LiteralPath $output) {
    throw 'Choose a new output directory to avoid replacing an existing ml.exe.'
}
if (-not $ConfigPath) {
    $candidates = @(
        (Join-Path $moduleDirectory 'config.json'),
        (Join-Path $repository 'cli-python/config.json'),
        (Join-Path $repository 'config.json')
    )
    $ConfigPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $ConfigPath) {
    throw 'Missing build config.json. Supply -ConfigPath or prepare cli-go/config.json.'
}
$source = (Resolve-Path -LiteralPath $ConfigPath).ProviderPath
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('wiserec-go-build-' + [Guid]::NewGuid().ToString('N'))
$snapshot = Join-Path $work 'config.json'
$overlay = Join-Path $work 'overlay.json'
$embedded = Join-Path $moduleDirectory 'internal/localstate/config.embedded.json'
$target = @{ GOOS = 'windows'; GOARCH = 'amd64'; CGO_ENABLED = '0' }
$previous = @{}

New-Item -ItemType Directory -Path $work | Out-Null
Push-Location $moduleDirectory
try {
    Copy-Item -LiteralPath $source -Destination $snapshot
    & go run ./cmd/check-config $snapshot
    if ($LASTEXITCODE -ne 0) {
        throw 'Go configuration check failed. For Go module download errors, see cli-go/README.md.'
    }

    # Build against a temporary replacement for the embed input. The checkout and
    # the published payload never receive a copy of the real configuration file.
    $replacement = @{ Replace = @{ $embedded = $snapshot } } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($overlay, $replacement)

    foreach ($name in $target.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $target[$name])
    }
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    & go build -trimpath -overlay $overlay -o $output ./cmd/ml
    if ($LASTEXITCODE -ne 0) { throw "Go build failed with exit code $LASTEXITCODE." }

    if ($PreflightPath) {
        & go build -trimpath -ldflags '-s -w -H=windowsgui' -o $PreflightPath ./cmd/msi-preflight
        if ($LASTEXITCODE -ne 0) { throw 'Building the MSI preflight failed.' }
    }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name])
    }
    Pop-Location
    Remove-Item -LiteralPath $work -Recurse -Force
}
Write-Output $output
