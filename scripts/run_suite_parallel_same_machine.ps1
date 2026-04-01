param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$Suite,
    [Parameter(Mandatory=$true)][string]$FlowDir,
    [string]$IncludeTag = "",
    [string]$AppId = "",
    [string]$ClearState = "true",
    [string]$MaestroCmd = "",
    [int]$RetryCount = 1
)

$ErrorActionPreference = "Stop"

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host "====================================="
    Write-Host $Text
    Write-Host "====================================="
}

function Read-DeviceIds([string]$RepoRoot) {
    $devices = @()
    $detectedFile = Join-Path $RepoRoot "detected_devices.txt"
    if (Test-Path -LiteralPath $detectedFile) {
        $lines = Get-Content -LiteralPath $detectedFile -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -and $_ -notmatch '^(List of devices attached|Devices detected:|Device list saved to:)' }
        foreach ($line in $lines) {
            if ($line -match '^\S+$') { $devices += $line }
        }
    }
    if ($devices.Count -gt 0) { return $devices | Select-Object -Unique }

    $adbOutput = & adb devices
    if ($LASTEXITCODE -ne 0) { throw "adb devices failed" }

    foreach ($line in $adbOutput) {
        if ($line -match '^(?<id>\S+)\s+device$') { $devices += $matches['id'] }
    }
    return $devices | Select-Object -Unique
}

function Quote-Arg([string]$s) {
    if ($null -eq $s) { return '""' }
    return '"' + ($s -replace '"','""') + '"'
}

function Run-ShardAllBatch(
    [string]$RepoRoot,
    [string]$Suite,
    [System.IO.FileInfo]$Flow,
    [string[]]$Devices,
    [string]$IncludeTag,
    [string]$MaestroCmd,
    [string]$Label,
    [string]$ReportsDir
) {
    $flowName = $Flow.BaseName
    $flowPath = $Flow.FullName
    $safeFlow = $flowName.Replace(' ', '_')
    $batchLog = Join-Path (Join-Path $ReportsDir "logs") ("{0}_{1}.log" -f $safeFlow, $Label.ToLower())
    $batchCsv = Join-Path (Join-Path $ReportsDir "results") ("{0}_{1}.csv" -f $safeFlow, $Label.ToLower())
    $deviceList = ($Devices -join ",")
    $shardCount = $Devices.Count

    Write-Section "$Label $flowName on devices"
    foreach ($d in $Devices) { Write-Host " - $d" }

    $args = @("test","--device",$deviceList,"--shard-all",$shardCount.ToString())
    if (-not [string]::IsNullOrWhiteSpace($IncludeTag)) {
        $args += @("--include-tags",$IncludeTag)
    }
    $args += @($flowPath)

    $argsString = ($args | ForEach-Object { Quote-Arg $_ }) -join " "
    $prettyCmd = "$MaestroCmd $argsString"

    New-Item -ItemType Directory -Force -Path (Join-Path $ReportsDir "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $ReportsDir "results") | Out-Null

    $header = @(
        "====================================="
        "RUN SHARD-ALL FLOW BATCH"
        "====================================="
        "Timestamp        : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Suite            : $Suite"
        "Flow path        : $flowPath"
        "Flow name        : $flowName"
        "Devices          : $deviceList"
        "Shard count      : $shardCount"
        "Include tag      : $IncludeTag"
        "Maestro cmd      : $prettyCmd"
        "====================================="
        ""
    )
    Set-Content -LiteralPath $batchLog -Value $header -Encoding UTF8

    & cmd.exe /c "$MaestroCmd $argsString" *> $batchLog
    $exitCode = $LASTEXITCODE

    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $reason = if ($exitCode -eq 0) { "OK" } else { "MAESTRO_BATCH_FAILED" }

    "suite,flow,device,status,exit_code,reason,log_file" | Set-Content -LiteralPath $batchCsv -Encoding Ascii
    foreach ($device in $Devices) {
        Add-Content -LiteralPath $batchCsv -Value ('{0},{1},{2},{3},{4},{5},"{6}"' -f $Suite, $flowName, $device, $status, $exitCode, $reason, $batchLog)
        Write-Host ("Device {0} -> ExitCode {1} -> BatchStatus {2} -> Log {3}" -f $device, $exitCode, $status, $batchLog)
    }

    return [pscustomobject]@{
        Flow = $flowName
        Devices = $Devices
        ExitCode = $exitCode
        Status = $status
        LogFile = $batchLog
    }
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$FlowRoot = Join-Path $RepoRoot $FlowDir
$ReportsDir = Join-Path $RepoRoot ("reports\" + $Suite)
$LogsDir = Join-Path $ReportsDir "logs"
$ResultsDir = Join-Path $ReportsDir "results"
$MasterCsv = Join-Path $ReportsDir "all_results.csv"
$DeviceSummaryCsv = Join-Path $ReportsDir "device_summary.csv"
$RetryCsv = Join-Path $ReportsDir "retry_summary.csv"

Write-Section "RUN SUITE SAME MACHINE PARALLEL (SHARD-ALL)"
Write-Host "Repo root: $RepoRoot"
Write-Host "Flow root: $FlowRoot"
Write-Host "Maestro cmd: $MaestroCmd"
Write-Host "Include tag: $IncludeTag"
Write-Host "Retry count: $RetryCount"

if (-not (Test-Path -LiteralPath $FlowRoot)) { Write-Host "ERROR: Flow directory not found: $FlowRoot"; exit 1 }

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$devices = Read-DeviceIds -RepoRoot $RepoRoot
Write-Host ""
Write-Host "Devices found: $($devices.Count)"
foreach ($d in $devices) { Write-Host " - $d" }
if ($devices.Count -eq 0) { Write-Host "ERROR: No connected devices found"; exit 1 }

$flowFiles = Get-ChildItem -LiteralPath $FlowRoot -Filter *.yaml -File | Sort-Object Name
if (-not $flowFiles -or $flowFiles.Count -eq 0) { Write-Host "ERROR: No yaml flows found in $FlowRoot"; exit 1 }

if ([string]::IsNullOrWhiteSpace($MaestroCmd)) { $MaestroCmd = "maestro" }

$overallFailed = $false
$retryRows = @()

foreach ($flow in $flowFiles) {
    $attempt1 = Run-ShardAllBatch -RepoRoot $RepoRoot -Suite $Suite -Flow $flow -Devices $devices -IncludeTag $IncludeTag -MaestroCmd $MaestroCmd -Label "Running" -ReportsDir $ReportsDir

    if ($attempt1.ExitCode -ne 0 -and $RetryCount -gt 0) {
        Write-Section "Retrying failed batch for $($flow.BaseName) on same devices"
        foreach ($d in $devices) { Write-Host " - $d" }

        $retry = Run-ShardAllBatch -RepoRoot $RepoRoot -Suite $Suite -Flow $flow -Devices $devices -IncludeTag $IncludeTag -MaestroCmd $MaestroCmd -Label "Retrying" -ReportsDir $ReportsDir

        foreach ($device in $devices) {
            $retryRows += [pscustomobject]@{
                flow = $flow.BaseName
                device = $device
                retry_exit_code = $retry.ExitCode
                retry_status = $retry.Status
                log_file = $retry.LogFile
            }
        }

        if ($retry.ExitCode -ne 0) {
            $overallFailed = $true
            Write-Host "Flow $($flow.BaseName) failed after retry"
        } else {
            Write-Host "Flow $($flow.BaseName) completed successfully after retry"
        }
    } elseif ($attempt1.ExitCode -ne 0) {
        $overallFailed = $true
        Write-Host "Flow $($flow.BaseName) failed"
    } else {
        Write-Host "Flow $($flow.BaseName) completed successfully"
    }
}

Write-Section "Merging result files"
"suite,flow,device,status,exit_code,reason,log_file" | Set-Content -Path $MasterCsv -Encoding Ascii
$tempCsvs = Get-ChildItem -LiteralPath $ResultsDir -Filter *.csv -File | Sort-Object Name
if (-not $tempCsvs -or $tempCsvs.Count -eq 0) { Write-Host "ERROR: No result CSV files were produced for suite $Suite"; exit 1 }

foreach ($csv in $tempCsvs) {
    $lines = Get-Content -LiteralPath $csv.FullName
    if ($lines.Count -gt 1) { $lines | Select-Object -Skip 1 | Add-Content -Path $MasterCsv }
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

if ($retryRows.Count -gt 0) {
    $retryRows | Export-Csv -LiteralPath $RetryCsv -NoTypeInformation
    Write-Host "Retry summary file: $RetryCsv"
}

Write-Host "Merged result file: $MasterCsv"
Write-Host "Device summary file: $DeviceSummaryCsv"
if ($overallFailed) { exit 1 } else { exit 0 }
