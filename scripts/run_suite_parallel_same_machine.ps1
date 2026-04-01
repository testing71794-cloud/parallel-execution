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

function Escape-CmdArg([string]$s) {
    if ($null -eq $s) { return '""' }
    return '"' + ($s.Replace('"', '""')) + '"'
}

function Build-RunnerCmdLine(
    [string]$RunnerBat,
    [string]$Suite,
    [string]$FlowPath,
    [string]$Device,
    [string]$AppId,
    [string]$ClearState,
    [string]$MaestroCmdArg,
    [string]$IncludeTagArg
) {
    $parts = @(
        "/c",
        "call",
        (Escape-CmdArg $RunnerBat),
        (Escape-CmdArg $Suite),
        (Escape-CmdArg $FlowPath),
        (Escape-CmdArg $Device),
        (Escape-CmdArg $AppId),
        (Escape-CmdArg $ClearState),
        (Escape-CmdArg $MaestroCmdArg),
        (Escape-CmdArg $IncludeTagArg)
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

function Test-ExecutionArtifacts([string]$StatusFile, [string]$ResultFile, [string]$LogFile) {
    if (-not (Test-Path -LiteralPath $StatusFile)) { return $false }
    if (-not (Test-Path -LiteralPath $ResultFile)) { return $false }
    if (-not (Test-Path -LiteralPath $LogFile)) { return $false }

    $statusText = Get-Content -LiteralPath $StatusFile -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($statusText)) { return $false }
    if ($statusText -match 'status\s*=\s*RUNNING') { return $false }

    $resultLines = @(Get-Content -LiteralPath $ResultFile -ErrorAction SilentlyContinue)
    if ($resultLines.Count -lt 2) { return $false }

    $logItem = Get-Item -LiteralPath $LogFile -ErrorAction SilentlyContinue
    if ($null -eq $logItem) { return $false }
    if ($logItem.Length -le 0) { return $false }

    return $true
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$FlowRoot = Join-Path $RepoRoot $FlowDir
$ScriptsDir = Join-Path $RepoRoot "scripts"
$RunnerBat = Join-Path $ScriptsDir "run_one_flow_on_device.bat"
$ReportsDir = Join-Path $RepoRoot ("reports\" + $Suite)
$LogsDir = Join-Path $ReportsDir "logs"
$ResultsDir = Join-Path $ReportsDir "results"
$StatusDir = Join-Path $RepoRoot "status"
$MasterCsv = Join-Path $ReportsDir "all_results.csv"
$DeviceSummaryCsv = Join-Path $ReportsDir "device_summary.csv"

Write-Section "RUN SUITE SAME MACHINE PARALLEL"
Write-Host "Repo root: $RepoRoot"
Write-Host "Flow root: $FlowRoot"
Write-Host "Runner bat: $RunnerBat"
Write-Host "Maestro cmd: $MaestroCmd"
Write-Host "Include tag: $IncludeTag"

if (-not (Test-Path -LiteralPath $RunnerBat)) {
    Write-Host "ERROR: Runner file not found: $RunnerBat"
    exit 1
}

if (-not (Test-Path -LiteralPath $FlowRoot)) {
    Write-Host "ERROR: Flow directory not found: $FlowRoot"
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $StatusDir | Out-Null

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
$IncludeTagArg = if ([string]::IsNullOrWhiteSpace($IncludeTag)) { "__EMPTY__" } else { $IncludeTag }
$MaestroCmdArg = if ([string]::IsNullOrWhiteSpace($MaestroCmd)) { "maestro" } else { $MaestroCmd }

foreach ($flow in $flowFiles) {
    $flowName = $flow.BaseName
    $flowPath = $flow.FullName

    Write-Section "Running $flowName on all devices"

    $flowFailed = $false
    $procInfos = @()
    foreach ($device in $devices) {
        $cmdLine = Build-RunnerCmdLine $RunnerBat $Suite $flowPath $device $AppId $ClearState $MaestroCmdArg $IncludeTagArg
        try {
            $p = Start-RunnerProcess -WorkingDir $RepoRoot -Arguments $cmdLine
            $procInfos += [pscustomobject]@{ Process = $p; Device = $device; Flow = $flowName }
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

        $safeFlow = $info.Flow.Replace(' ', '_')
        $safeDevice = $info.Device.Replace(' ', '_')
        $statusFile = Join-Path $StatusDir ("{0}__{1}__{2}.txt" -f $Suite, $safeFlow, $safeDevice)
        $resultFile = Join-Path $ResultsDir ("{0}_{1}.csv" -f $safeFlow, $safeDevice)
        $logFile = Join-Path $LogsDir ("{0}_{1}.log" -f $safeFlow, $safeDevice)

        $artifactsOk = Test-ExecutionArtifacts -StatusFile $statusFile -ResultFile $resultFile -LogFile $logFile
        Write-Host ("Device {0} -> ExitCode {1} -> ArtifactsOk {2} -> Log {3}" -f $info.Device, $code, $artifactsOk, $logFile)

        if (($code -ne 0) -or (-not $artifactsOk)) {
            $flowFailed = $true
            $overallFailed = $true
        }
        try { $info.Process.Dispose() } catch {}
    }

    if ($flowFailed) {
        Write-Host "Flow $flowName failed on one or more devices"
    } else {
        Write-Host "Flow $flowName completed successfully on all devices"
    }
}

Write-Section "Merging per-device result files"
"suite,flow,device,status,exit_code,reason,log_file" | Set-Content -Path $MasterCsv -Encoding Ascii
$tempCsvs = Get-ChildItem -LiteralPath $ResultsDir -Filter *.csv -File | Sort-Object Name

if (-not $tempCsvs -or $tempCsvs.Count -eq 0) {
    Write-Host "ERROR: No per-device result CSV files were produced for suite $Suite"
    exit 1
}

foreach ($csv in $tempCsvs) {
    $lines = Get-Content -LiteralPath $csv.FullName
    if ($lines.Count -gt 1) {
        $lines | Select-Object -Skip 1 | Add-Content -Path $MasterCsv
    }
}

$statusFiles = @(Get-ChildItem -LiteralPath $StatusDir -Filter ("{0}__*.txt" -f $Suite) -File -ErrorAction SilentlyContinue)
if (-not $statusFiles -or $statusFiles.Count -eq 0) {
    Write-Host "ERROR: No status files were produced for suite $Suite"
    exit 1
}

$rows = Import-Csv -LiteralPath $MasterCsv
$summary = $rows |
    Group-Object device |
    ForEach-Object {
        $deviceRows = $_.Group
        $passCount = @($deviceRows | Where-Object { $_.status -eq 'PASS' }).Count
        $failCount = @($deviceRows | Where-Object { $_.status -ne 'PASS' }).Count
        [pscustomobject]@{
            device = $_.Name
            total_flows = $deviceRows.Count
            passed = $passCount
            failed = $failCount
            overall_status = $(if ($failCount -gt 0) { 'FAIL' } else { 'PASS' })
        }
    } | Sort-Object device

$summary | Export-Csv -LiteralPath $DeviceSummaryCsv -NoTypeInformation

Write-Host "Merged result file: $MasterCsv"
Write-Host "Device summary file: $DeviceSummaryCsv"
if ($overallFailed) { exit 1 } else { exit 0 }
