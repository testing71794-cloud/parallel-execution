#Requires -Version 5.1
<#
.SYNOPSIS
  Read-only disk footprint for Jenkins automation (workspace, jobs/builds, caches, Maestro, TEMP).

.NOTES
  Does not delete anything. Large Jenkins homes may take a minute to scan.
#>
[CmdletBinding()]
param(
    [string] $Workspace = $env:WORKSPACE,
    [string] $JenkinsHome = $env:JENKINS_HOME
)

function Get-FolderSizeMB {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $sum = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue
        if ($null -eq $sum -or $null -eq $sum.Sum) { return 0 }
        return [math]::Round($sum.Sum / 1MB, 2)
    } catch {
        return $null
    }
}

function Write-SizeLine {
    param([string] $Label, [string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        Write-Host ("[size] {0} = (path not set)" -f $Label)
        return
    }
    $mb = Get-FolderSizeMB -Path $Path
    if ($null -eq $mb) {
        Write-Host ("[size] {0} = not found or unreadable: {1}" -f $Label, $Path)
    } else {
        Write-Host ("[size] {0} ~ {1} MB" -f $Label, $mb)
    }
}

Write-Host "=== check_disk_usage.ps1 (read-only) ==="

Write-SizeLine "Jenkins workspace" $Workspace

if (-not [string]::IsNullOrWhiteSpace($JenkinsHome) -and (Test-Path -LiteralPath $JenkinsHome)) {
    $jobsRoot = Join-Path $JenkinsHome "jobs"
    Write-SizeLine "Jenkins HOME (total)" $JenkinsHome
    Write-SizeLine "Jenkins jobs folder" $jobsRoot

    # Approximate size of per-job build logs + archived artifacts under jobs/*/builds
    $buildsMb = 0.0
    if (Test-Path -LiteralPath $jobsRoot) {
        Get-ChildItem -LiteralPath $jobsRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $bd = Join-Path $_.FullName "builds"
            if (Test-Path -LiteralPath $bd) {
                $s = Get-ChildItem -LiteralPath $bd -Recurse -File -Force -ErrorAction SilentlyContinue |
                    Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue
                if ($null -ne $s -and $null -ne $s.Sum) { $buildsMb += [double]($s.Sum / 1MB) }
            }
        }
        Write-Host ("[size] Jenkins jobs/*/builds (approx, artifacts+log) ~ {0} MB" -f [math]::Round($buildsMb, 2))
    }

    $wsDir = Join-Path $JenkinsHome "workspace"
    Write-SizeLine "Jenkins workspace dir under HOME" $wsDir
} else {
    Write-Host "[size] JENKINS_HOME = not set or missing (typical on agents; set on controller to measure)"
}

$npmCache = Join-Path $env:LOCALAPPDATA "npm-cache"
Write-SizeLine "npm cache" $npmCache

$pipCache = Join-Path $env:LOCALAPPDATA "pip\Cache"
Write-SizeLine "pip cache" $pipCache

$maestroUser = Join-Path $env:USERPROFILE ".maestro"
Write-SizeLine "User .maestro" $maestroUser

Write-SizeLine "User TEMP" $env:TEMP

Write-Host "=== end disk usage report ==="
