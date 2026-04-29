# ATP TestCase Flows — recursive Maestro runs (folder name = logical suite for reporting).
# Does not modify existing run_suite_parallel_same_machine.ps1 (Printing / Non-printing unchanged).

param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [string]$AppId = "",
    [string]$ClearState = "true",
    [string]$MaestroCmd = ""
)

$ErrorActionPreference = "Stop"

function Add-AdbFromEnvToPath {
    if ([string]::IsNullOrWhiteSpace($env:ADB_HOME)) { return }
    $d = $env:ADB_HOME.Trim()
    if (-not (Test-Path -LiteralPath (Join-Path $d "adb.exe"))) { return }
    if ($env:Path -and ($env:Path -split ';') -contains $d) { return }
    if ($env:Path -and ($env:Path -split ';') -contains $d.TrimEnd('\')) { return }
    $env:Path = $d + ";" + $env:Path
}

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host "====================================="
    Write-Host $Text
    Write-Host "====================================="
}

function Quote-Arg([string]$s) {
    if ($null -eq $s) { return '""' }
    return '"' + ($s -replace '"', '""') + '"'
}

function Resolve-MaestroLauncherPath {
    if ([string]::IsNullOrWhiteSpace($env:MAESTRO_HOME)) {
        throw "MAESTRO_HOME is not set."
    }
    $h = $env:MAESTRO_HOME.Trim()
    $bat = Join-Path $h "maestro.bat"
    if (Test-Path -LiteralPath $bat) { return (Resolve-Path -LiteralPath $bat).Path }
    $cmdf = Join-Path $h "maestro.cmd"
    if (Test-Path -LiteralPath $cmdf) { return (Resolve-Path -LiteralPath $cmdf).Path }
    throw "maestro.bat / maestro.cmd not found under MAESTRO_HOME: $h"
}

function Get-AuthorizedSerialsFromAdb {
    $out = [System.Collections.Generic.List[string]]::new()
    if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
        throw "adb not on PATH."
    }
    $raw = & adb devices
    if ($LASTEXITCODE -ne 0) { throw "adb devices failed (exit $LASTEXITCODE)" }
    foreach ($line in $raw) {
        if ($line -match '^(?<s>\S+)\s+device\s*$') { $out.Add($matches['s'].Trim()) }
    }
    return $out
}

function Read-DetectedFileSerials([string]$R) {
    $detected = Join-Path $R "detected_devices.txt"
    if (-not (Test-Path -LiteralPath $detected)) { return @() }
    $lines = Get-Content -LiteralPath $detected -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and $_ -notmatch '^(List of devices attached|Devices detected:|Device list saved to:)' }
    $r = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $lines) { if ($line -match '^\S+$') { if (-not $r.Contains($line)) { $r.Add($line) } } }
    return $r
}

function Merge-AndPickDevices {
    param([string]$RepoRoot)
    $authorized = [array](Get-AuthorizedSerialsFromAdb)
    if ($authorized.Count -eq 0) {
        throw "No Android devices in state 'device'."
    }
    $fileSerials = [array](Read-DetectedFileSerials $RepoRoot)
    if ($fileSerials.Count -eq 0) { return $authorized }
    $picked = @()
    foreach ($s in $fileSerials) { if ($authorized -contains $s) { $picked += $s } }
    if ($picked.Count -eq 0) {
        throw "detected_devices.txt has no serials currently authorized as device."
    }
    return $picked
}

function Start-RunOneOnDevice {
    param(
        [string]$R,
        [string]$Suite,
        [string]$FlowPath,
        [string]$DeviceId,
        [string]$App,
        [string]$Clr,
        [string]$MaestroPath,
        [string]$TagOrEmpty
    )
    $runOne = [System.IO.Path]::GetFullPath((Join-Path $R "scripts\run_one_flow_on_device.bat"))
    $t = if ([string]::IsNullOrWhiteSpace($TagOrEmpty)) { "__EMPTY__" } else { $TagOrEmpty }
    $cmd = "call {0} {1} {2} {3} {4} {5} {6} {7}" -f @(
        (Quote-Arg $runOne),
        (Quote-Arg $Suite),
        (Quote-Arg $FlowPath),
        (Quote-Arg $DeviceId),
        (Quote-Arg $App),
        (Quote-Arg $Clr),
        (Quote-Arg $MaestroPath),
        (Quote-Arg $t)
    )
    $full = "cd /d " + (Quote-Arg $R) + " && " + $cmd
    return Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $full) -NoNewWindow -PassThru
}

function Get-AtpFolderName([string]$atpRoot, [string]$filePath) {
    $rootFull = [System.IO.Path]::GetFullPath($atpRoot)
    $fileFull = [System.IO.Path]::GetFullPath($filePath)
    if (-not $fileFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        return "_Invalid"
    }
    $rest = $fileFull.Substring($rootFull.Length).TrimStart([char[]]@('\', '/'))
    if ([string]::IsNullOrWhiteSpace($rest)) { return "_Root" }
    $first = ($rest -split '[\\/]', 2)[0]
    if ($first -match '\.(yaml|yml)$') { return "_Root" }
    return $first
}

function Get-AtpSuiteId([string]$folderName) {
    $t = $folderName.Trim() -replace '[^a-zA-Z0-9]+', '_'
    $t = $t.Trim('_').ToLower()
    if ([string]::IsNullOrWhiteSpace($t)) { $t = "unknown" }
    return "atp_$t"
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$atpRoot = Join-Path $RepoRoot "ATP TestCase Flows"

Write-Section "ATP TestCase Flows"
Write-Host "Repo root: $RepoRoot"
Write-Host "ATP root:  $atpRoot"

if (-not (Test-Path -LiteralPath $atpRoot)) {
    Write-Host "[ATP] SKIP: folder not found — ATP TestCase Flows"
    exit 0
}

$flowFiles = @(Get-ChildItem -LiteralPath $atpRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { @('.yaml', '.yml') -contains $_.Extension.ToLowerInvariant() } |
    Sort-Object FullName)

if (-not $flowFiles -or $flowFiles.Count -eq 0) {
    Write-Host "[ATP] SKIP: no .yaml/.yml files under ATP TestCase Flows"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($AppId)) {
    Write-Host "ERROR: AppId required"
    exit 1
}
if ([string]::IsNullOrWhiteSpace($ClearState)) { $ClearState = "true" }

Add-AdbFromEnvToPath
$null = cmd /c "adb start-server 2>nul"
$null = cmd /c "adb devices 1>nul 2>nul"
Start-Sleep -Seconds 1

try {
    $devices = [array](Merge-AndPickDevices $RepoRoot)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}

Write-Host "Devices: $($devices -join ', ')"
$maestroLaunch = Resolve-MaestroLauncherPath
Write-Host "Maestro: $maestroLaunch"

New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "status") | Out-Null

$labels = @{}
$overallFailed = $false

foreach ($flow in $flowFiles) {
    $folderName = Get-AtpFolderName $atpRoot $flow.FullName
    $suiteId = Get-AtpSuiteId $folderName
    $labels[$suiteId] = $folderName
    $flowBase = $flow.BaseName
    Write-Section "ATP [$folderName] :: $flowBase (suite=$suiteId)"
    foreach ($dev in $devices) {
        Write-Host "  device $dev"
        $rd = Join-Path $RepoRoot ("reports\" + $suiteId)
        New-Item -ItemType Directory -Force -Path (Join-Path $rd "logs") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $rd "results") | Out-Null
        $p = Start-RunOneOnDevice -R $RepoRoot -Suite $suiteId -FlowPath $flow.FullName -DeviceId $dev -App $AppId -Clr $ClearState -MaestroPath $maestroLaunch -TagOrEmpty "__EMPTY__"
        if (-not $p.HasExited) { $p.WaitForExit() }
        $ex = if ($null -ne $p.ExitCode) { [int]$p.ExitCode } else { 1 }
        if ($ex -ne 0) {
            $overallFailed = $true
            Write-Host "  [FAIL] exit=$ex device=$dev flow=$flowBase"
        } else {
            Write-Host "  [OK] exit=$ex device=$dev"
        }
    }
}

$bs = Join-Path $RepoRoot "build-summary"
New-Item -ItemType Directory -Force -Path $bs | Out-Null
$labelsPath = Join-Path $bs "atp_suite_labels.json"
$labels | ConvertTo-Json -Compress | Set-Content -LiteralPath $labelsPath -Encoding UTF8
Write-Host "[ATP] Wrote suite labels: $labelsPath"

if ($overallFailed) {
    Write-Host "[ATP] Completed with failures."
    exit 1
}
Write-Host "[ATP] All flows passed."
exit 0
