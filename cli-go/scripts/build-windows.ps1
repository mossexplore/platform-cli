param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
$moduleDirectory = Split-Path $PSScriptRoot
$repository = Split-Path $moduleDirectory
$versionLine = Select-String -Path (Join-Path $repository 'versions.toml') -Pattern '^cli = "([0-9]+(?:\.[0-9]+){2,3})"$'
if (@($versionLine).Count -ne 1) {
    throw 'versions.toml must contain exactly one CLI version.'
}

$version = $versionLine.Matches[0].Groups[1].Value
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
    & go build -trimpath -ldflags "-X main.version=$version" -o $output ./cmd/ml
    if ($LASTEXITCODE -ne 0) {
        throw "Go build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
    foreach ($name in $previous.Keys) {
        [System.Environment]::SetEnvironmentVariable($name, $previous[$name])
    }
}
Write-Output $output
