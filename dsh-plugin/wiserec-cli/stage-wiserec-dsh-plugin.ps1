[CmdletBinding()]
param(
    [string] $InstallRoot = (Join-Path $env:LOCALAPPDATA 'WiseRec\dsh-plugins\wiserec-cli')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'release.json') | ConvertFrom-Json
if ($manifest.version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
    throw 'Invalid WiseRec plugin version'
}
$name = "dsh-wiserec-cli-$($manifest.version).tgz"
$source = Join-Path $PSScriptRoot $name
$actual = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if ($actual -ne $manifest.bundle_sha256) {
    throw 'WiseRec plugin bundle checksum mismatch'
}
$destination = Join-Path $InstallRoot $manifest.version
$null = New-Item -ItemType Directory -Path $destination -Force
$bundle = Join-Path $destination $name
if (Test-Path -LiteralPath $bundle) {
    if ((Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash -ne $actual) {
        throw 'A different bundle already exists at this version'
    }
} else {
    $temporary = Join-Path $destination ([Guid]::NewGuid().ToString() + '.tmp')
    try {
        Copy-Item -LiteralPath $source -Destination $temporary
        if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne $actual) {
            throw 'The staged bundle checksum does not match'
        }
        [System.IO.File]::Move($temporary, $bundle)
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary
        }
    }
}
(Resolve-Path -LiteralPath $bundle).Path
