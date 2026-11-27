Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-SafePathSegment([string] $Segment) {
    if ([string]::IsNullOrEmpty($Segment) -or $Segment -match '[<>:"/\\|?*\x00-\x1f]' -or
        $Segment -match '[. ]$' -or $Segment -match '^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3]) *(?:\.|$)') {
        throw "Invalid Windows path segment in Skill archive: '$Segment'"
    }
}

function Expand-BusinessSkill($Zip, [string] $Destination) {
    $name = $Zip.BaseName
    Assert-SafePathSegment $name
    $archive = [IO.Compression.ZipFile]::OpenRead($Zip.FullName)
    try {
        foreach ($entry in $archive.Entries) {
            $relative = $entry.FullName.Replace('\', '/')
            $isDirectory = $relative.EndsWith('/')
            $parts = $relative.TrimEnd('/').Split('/')
            foreach ($part in $parts) { Assert-SafePathSegment $part }
            if ($parts[0] -cne $name -or ($parts.Count -eq 1 -and -not $isDirectory)) {
                throw "$($Zip.Name) must contain a single top-level folder named '$name'. Found '$relative'."
            }

            $target = $Destination
            foreach ($part in $parts) { $target = Join-Path $target $part }
            if ($isDirectory) {
                [void] [IO.Directory]::CreateDirectory($target)
                continue
            }
            [void] [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
        }
    } finally {
        $archive.Dispose()
    }

    $source = Join-Path $Destination $name
    $entryPoint = Join-Path $source 'SKILL.md'
    if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf) -or (Get-Item -LiteralPath $entryPoint).Length -eq 0) {
        throw "$($Zip.Name) is missing a non-empty $name/SKILL.md."
    }
    return $source
}

function Assert-PlainDirectory([string] $Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -ne $item -and (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint))) {
        throw "Expected a regular directory at '$Path'."
    }
}

function Remove-Workspace([string] $Path) {
    try {
        if ([IO.Directory]::Exists($Path)) { [IO.Directory]::Delete($Path, $true) }
    } catch {
        Write-Warning "Could not clean temporary files at '$Path': $_"
    }
}

function Install-BusinessSkill([string] $Source, [string[]] $Roots) {
    $name = [IO.Path]::GetFileName($Source)
    $slots = @()
    try {
        # Stage complete copies on the destination volumes before touching any existing Skill.
        foreach ($root in $Roots) {
            $parent = [IO.Path]::GetDirectoryName($root)
            Assert-PlainDirectory $parent
            Assert-PlainDirectory $root
            $target = Join-Path $root $name
            Assert-PlainDirectory $target
            [void] [IO.Directory]::CreateDirectory($root)
            $work = Join-Path $parent ('.wiserec-skill-' + [Guid]::NewGuid().ToString('N'))
            $slot = @{
                Target = $target
                Work = $work
                Staged = Join-Path $work 'new'
                Backup = Join-Path $work 'previous'
                BackedUp = $false
                Installed = $false
                KeepWorkspace = $false
            }
            $slots += $slot
            [void] [IO.Directory]::CreateDirectory($work)
            Copy-Item -LiteralPath $Source -Destination $slot.Staged -Recurse -Force
        }
        foreach ($slot in $slots) {
            if ([IO.Directory]::Exists($slot.Target)) {
                [IO.Directory]::Move($slot.Target, $slot.Backup)
                $slot.BackedUp = $true
            }
            [IO.Directory]::Move($slot.Staged, $slot.Target)
            $slot.Installed = $true
        }
    } catch {
        for ($i = $slots.Count - 1; $i -ge 0; $i--) {
            $slot = $slots[$i]
            try {
                if ($slot.Installed) { [IO.Directory]::Move($slot.Target, $slot.Staged) }
                if ($slot.BackedUp) { [IO.Directory]::Move($slot.Backup, $slot.Target) }
            } catch {
                $slot.KeepWorkspace = $true
                Write-Warning "Could not restore '$($slot.Target)'. Recovery files are at '$($slot.Work)': $_"
            }
        }
        throw
    } finally {
        foreach ($slot in $slots) {
            if (-not $slot.KeepWorkspace) { Remove-Workspace $slot.Work }
        }
    }

    foreach ($slot in $slots) { Write-Host "Installed $name -> $($slot.Target)" }
}

$workspace = $null
$mutex = $null
$ownsMutex = $false
try {
    $businessRoot = Split-Path -Parent $PSScriptRoot
    $archives = @(Get-ChildItem -LiteralPath $businessRoot -Filter '*.zip' -File | Sort-Object Name)
    if ($archives.Count -eq 0) {
        Write-Host "No business Skill ZIP files found in '$businessRoot'."
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($env:USERPROFILE) -or -not [IO.Path]::IsPathRooted($env:USERPROFILE)) {
        throw 'USERPROFILE does not point to a user profile directory.'
    }
    $roots = @(
        (Join-Path $env:USERPROFILE '.agents/skills')
        (Join-Path $env:USERPROFILE '.cac/skills')
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $workspace = Join-Path ([IO.Path]::GetTempPath()) ('wiserec-business-skills-' + [Guid]::NewGuid().ToString('N'))
    [void] [IO.Directory]::CreateDirectory($workspace)
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $sources = @(foreach ($zip in $archives) {
        if (-not $names.Add($zip.BaseName)) {
            throw "More than one ZIP uses the Skill name '$($zip.BaseName)'."
        }
        try {
            Expand-BusinessSkill $zip $workspace
        } catch {
            throw "Could not extract '$($zip.Name)': $($_.Exception.Message)"
        }
    })

    $mutex = [Threading.Mutex]::new($false, 'WiseRec.BusinessSkillInstaller')
    try {
        $ownsMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }
    if (-not $ownsMutex) { throw 'Another business Skill installation is running.' }

    $installed = 0
    foreach ($source in $sources) {
        try {
            Install-BusinessSkill $source $roots
            $installed++
        } catch {
            [Console]::Error.WriteLine("Could not install '$([IO.Path]::GetFileName($source))': $($_.Exception.Message)")
        }
    }
    Write-Host "Installed $installed of $($sources.Count) business Skill(s)."
    if ($installed -ne $sources.Count) { exit 1 }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
    if ($null -ne $workspace) { Remove-Workspace $workspace }
}
