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

foreach ($flow in $flowFiles) {
    $flowName = $flow.BaseName
    $flowPath = $flow.FullName

    Write-Section "Running $flowName on all devices"

    # Start-Job breaks adb/Maestro on many Jenkins agents (no inherited PATH/session).
    # Parallel real processes inherit this session's environment.
    $procInfos = @()
    foreach ($device in $devices) {
        $p = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @(
                '/c', 'call', $RunnerBat,
                $Suite,
                $flowPath,
                $flowName,
                $device,
                $AppId,
                $ClearState,
                $IncludeTag,
                $MaestroCmd
            ) `
            -WorkingDirectory $RepoRoot `
            -PassThru `
            -NoNewWindow
        $procInfos += [pscustomobject]@{ Process = $p; Device = $device }
    }

    $flowFailed = $false
    foreach ($info in $procInfos) {
        try {
            $info.Process.WaitForExit()
            $code = $info.Process.ExitCode
        } catch {
            Write-Host "ERROR waiting for process: $_"
            $code = 1
        }
        Write-Host ("Device {0} -> ExitCode {1}" -f $info.Device, $code)
        if ([int]$code -ne 0) {
            $flowFailed = $true
            $overallFailed = $true
        }
    }

    if ($flowFailed) {
        Write-Host "Flow $flowName failed on one or more devices"
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
