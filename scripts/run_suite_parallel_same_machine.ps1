# Execution order: flow1.yaml on EVERY device at the same time -> wait until all finish ->
# flow2.yaml on every device at the same time -> ... (sorted by file name).
# Non-printing and printing suites both use this script via run_suite_parallel_same_machine.bat

param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$Suite,
    [Parameter(Mandatory=$true)][string]$FlowDir,
    [string]$IncludeTag = "",
    [string]$AppId = "",
    [string]$ClearState = "true",
    [string]$MaestroCmd = ""
)

$ErrorActionPreference = "Stop"

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host "====================================="
    Write-Host $Text
    Write-Host "====================================="
}

# cmd.exe splits the command line on spaces unless args are quoted; paths like
# "Non printing flows\flow1.yaml" must be one argv or %~2 in the batch becomes "C:\...\Non" only.
function Escape-CmdArg([string]$s) {
    if ($null -eq $s) { return '""' }
    return '"' + ($s.Replace('"', '""')) + '"'
}

# Build one cmd.exe command line (spaces in paths; Start-Process -PassThru often leaves ExitCode null on Win PS 5.x).
function Build-RunnerCmdLine([string]$RunnerBat, [string]$Suite, [string]$FlowPath, [string]$FlowName, [string]$Device, [string]$AppId, [string]$ClearState, [string]$IncludeTagArg, [string]$MaestroCmdArg) {
    $parts = @(
        "/c",
        "call",
        (Escape-CmdArg $RunnerBat),
        (Escape-CmdArg $Suite),
        (Escape-CmdArg $FlowPath),
        (Escape-CmdArg $FlowName),
        (Escape-CmdArg $Device),
        (Escape-CmdArg $AppId),
        (Escape-CmdArg $ClearState),
        (Escape-CmdArg $IncludeTagArg),
        (Escape-CmdArg $MaestroCmdArg)
    )
    return ($parts -join " ")
}

function Start-RunnerProcess([string]$WorkingDir, [string]$Arguments) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    return $p
}

function Get-ProcessExitCodeSafe([System.Diagnostics.Process]$p) {
    if (-not $p.HasExited) {
        $p.WaitForExit()
    }
    try { $p.Refresh() | Out-Null } catch {}
    $ec = $p.ExitCode
    if ($null -ne $ec) { return [int]$ec }
    return -1
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$FlowRoot = Join-Path $RepoRoot $FlowDir
$ScriptsDir = Join-Path $RepoRoot "scripts"
$RunnerBat = Join-Path $ScriptsDir "run_one_flow_on_device.bat"
$ReportsDir = Join-Path $RepoRoot ("reports\" + $Suite)
$ResultsDir = Join-Path $ReportsDir "results"
$MasterCsv = Join-Path $ReportsDir "all_results.csv"

Write-Section "RUN SUITE SAME MACHINE PARALLEL"
Write-Host "Repo root: $RepoRoot"
Write-Host "Flow root: $FlowRoot"
Write-Host "Runner bat: $RunnerBat"
Write-Host "Maestro cmd: $MaestroCmd"

if (-not (Test-Path -LiteralPath $RunnerBat)) {
    Write-Host "ERROR: Runner file not found: $RunnerBat"
    exit 1
}

if (-not (Test-Path -LiteralPath $FlowRoot)) {
    Write-Host "ERROR: Flow directory not found: $FlowRoot"
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$adbOutput = & adb devices
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: adb devices failed"
    exit 1
}

$devices = @()
foreach ($line in $adbOutput) {
    if ($line -match '^(?<id>\S+)\s+device$') {
        $devices += $matches['id']
    }
}

Write-Host ""
Write-Host "Devices found: $($devices.Count)"
foreach ($d in $devices) {
    Write-Host " - $d"
}

if ($devices.Count -eq 0) {
    Write-Host "ERROR: No connected devices found"
    exit 1
}

$flowFiles = Get-ChildItem -LiteralPath $FlowRoot -Filter *.yaml -File | Sort-Object Name
if (-not $flowFiles -or $flowFiles.Count -eq 0) {
    Write-Host "ERROR: No yaml flows found in $FlowRoot"
    exit 1
}

$overallFailed = $false

# Start-Process -ArgumentList cannot contain null or empty strings on Windows PowerShell 5.x
# (Jenkins passes "" for optional INCLUDE_TAG / MAESTRO_CMD). Use a sentinel the bat strips.
$IncludeTagArg = if ([string]::IsNullOrWhiteSpace($IncludeTag)) { "__EMPTY__" } else { $IncludeTag }
$MaestroCmdArg = if ([string]::IsNullOrWhiteSpace($MaestroCmd)) { "__EMPTY__" } else { $MaestroCmd }

foreach ($flow in $flowFiles) {
    $flowName = $flow.BaseName
    $flowPath = $flow.FullName

    Write-Section "Running $flowName on all devices"
    Write-Host "Pattern: this flow runs on ALL $($devices.Count) device(s) in parallel; the next flow starts only after every device finishes this one."

    $flowFailed = $false
    # Start-Job breaks adb/Maestro on many Jenkins agents. Use System.Diagnostics.Process for reliable ExitCode.
    $procInfos = @()
    foreach ($device in $devices) {
        $cmdLine = Build-RunnerCmdLine $RunnerBat $Suite $flowPath $flowName $device $AppId $ClearState $IncludeTagArg $MaestroCmdArg
        try {
            $p = Start-RunnerProcess -WorkingDir $RepoRoot -Arguments $cmdLine
            $procInfos += [pscustomobject]@{ Process = $p; Device = $device }
        } catch {
            Write-Host "ERROR starting process for ${device}: $_"
            $overallFailed = $true
            $flowFailed = $true
        }
    }

    foreach ($info in $procInfos) {
        try {
            $code = Get-ProcessExitCodeSafe $info.Process
        } catch {
            Write-Host "ERROR waiting for process $($info.Device): $_"
            $code = -1
        }
        Write-Host ("Device {0} -> ExitCode {1}" -f $info.Device, $code)
        if ($code -ne 0) {
            $flowFailed = $true
            $overallFailed = $true
        }
        try { $info.Process.Dispose() } catch {}
    }

    if ($flowFailed) {
        Write-Host "Flow $flowName failed on one or more devices"
        Write-Host "Check Maestro logs: $ReportsDir\logs\${flowName}_*.log (ExitCode 1 = test or Maestro failure, not Jenkins)."
    } else {
        Write-Host "Flow $flowName completed successfully on all devices"
    }
}

Write-Section "Merging per-device result files"

"suite,flow_name,device_id,status,exit_code,log_file" | Set-Content -Path $MasterCsv -Encoding Ascii
$tempCsvs = Get-ChildItem -LiteralPath $ResultsDir -Filter *.csv -File | Sort-Object Name

foreach ($csv in $tempCsvs) {
    $lines = Get-Content -LiteralPath $csv.FullName
    if ($lines.Count -gt 1) {
        $lines | Select-Object -Skip 1 | Add-Content -Path $MasterCsv
    }
}

Write-Host "Merged result file: $MasterCsv"

if ($overallFailed) { exit 1 } else { exit 0 }
