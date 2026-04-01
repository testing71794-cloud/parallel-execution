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
    if (-not $p.HasExited) { $p.WaitForExit() }
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
    if ($LASTEXITCODE -ne 0) {
        throw "adb devices failed"
    }

    foreach ($line in $adbOutput) {
        if ($line -match '^(?<id>\S+)\s+device$') {
            $devices += $matches['id']
        }
    }
    return $devices | Select-Object -Unique
}

function Run-FlowBatch([string]$RepoRoot,[string]$Suite,[System.IO.FileInfo]$Flow,[string[]]$Devices,[string]$AppId,[string]$ClearState,[string]$MaestroCmdArg,[string]$IncludeTagArg) {
    $ScriptsDir = Join-Path $RepoRoot "scripts"
    $RunnerBat = Join-Path $ScriptsDir "run_one_flow_on_device.bat"
    $StatusDir = Join-Path $RepoRoot "status"
    $ReportsDir = Join-Path $RepoRoot ("reports\" + $Suite)
    $LogsDir = Join-Path $ReportsDir "logs"
    $ResultsDir = Join-Path $ReportsDir "results"

    $flowName = $Flow.BaseName
    $flowPath = $Flow.FullName

    Write-Section "Running $flowName on all devices"

    $procInfos = @()
    foreach ($device in $Devices) {
        $cmdLine = Build-RunnerCmdLine $RunnerBat $Suite $flowPath $device $AppId $ClearState $MaestroCmdArg $IncludeTagArg
        try {
            $p = Start-RunnerProcess -WorkingDir $RepoRoot -Arguments $cmdLine
            $procInfos += [pscustomobject]@{ Process = $p; Device = $device; Flow = $flowName; FlowPath = $flowPath }
        } catch {
            Write-Host "ERROR starting process for ${device}: $_"
            $procInfos += [pscustomobject]@{ Process = $null; Device = $device; Flow = $flowName; FlowPath = $flowPath; FailedToStart = $true }
        }
    }

    $results = @()
    foreach ($info in $procInfos) {
        $safeFlow = $info.Flow.Replace(' ', '_')
        $safeDevice = $info.Device.Replace(' ', '_')
        $statusFile = Join-Path $StatusDir ("{0}__{1}__{2}.txt" -f $Suite, $safeFlow, $safeDevice)
        $resultFile = Join-Path $ResultsDir ("{0}_{1}.csv" -f $safeFlow, $safeDevice)
        $logFile = Join-Path $LogsDir ("{0}_{1}.log" -f $safeFlow, $safeDevice)

        if ($info.FailedToStart) {
            $results += [pscustomobject]@{
                Device = $info.Device; Flow = $info.Flow; FlowPath = $info.FlowPath
                ExitCode = -1; ArtifactsOk = $false; LogFile = $logFile; Passed = $false
            }
            continue
        }

        try {
            $code = Get-ProcessExitCodeSafe $info.Process
        } catch {
            Write-Host "ERROR waiting for process $($info.Device): $_"
            $code = -1
        }

        $artifactsOk = Test-ExecutionArtifacts -StatusFile $statusFile -ResultFile $resultFile -LogFile $logFile
        Write-Host ("Device {0} -> ExitCode {1} -> ArtifactsOk {2} -> Log {3}" -f $info.Device, $code, $artifactsOk, $logFile)

        $results += [pscustomobject]@{
            Device = $info.Device; Flow = $info.Flow; FlowPath = $info.FlowPath
            ExitCode = $code; ArtifactsOk = $artifactsOk; LogFile = $logFile
            Passed = (($code -eq 0) -and $artifactsOk)
        }

        try { $info.Process.Dispose() } catch {}
    }
    return $results
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$FlowRoot = Join-Path $RepoRoot $FlowDir
$ReportsDir = Join-Path $RepoRoot ("reports\" + $Suite)
$LogsDir = Join-Path $ReportsDir "logs"
$ResultsDir = Join-Path $ReportsDir "results"
$MasterCsv = Join-Path $ReportsDir "all_results.csv"
$DeviceSummaryCsv = Join-Path $ReportsDir "device_summary.csv"
$RetryCsv = Join-Path $ReportsDir "retry_summary.csv"

Write-Section "RUN SUITE SAME MACHINE PARALLEL"
Write-Host "Repo root: $RepoRoot"
Write-Host "Flow root: $FlowRoot"
Write-Host "Maestro cmd: $MaestroCmd"
Write-Host "Include tag: $IncludeTag"
Write-Host "Retry count: $RetryCount"

if (-not (Test-Path -LiteralPath $FlowRoot)) {
    Write-Host "ERROR: Flow directory not found: $FlowRoot"
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$devices = Read-DeviceIds -RepoRoot $RepoRoot
Write-Host ""
Write-Host "Devices found: $($devices.Count)"
foreach ($d in $devices) { Write-Host " - $d" }

if ($devices.Count -eq 0) {
    Write-Host "ERROR: No connected devices found"
    exit 1
}

$flowFiles = Get-ChildItem -LiteralPath $FlowRoot -Filter *.yaml -File | Sort-Object Name
if (-not $flowFiles -or $flowFiles.Count -eq 0) {
    Write-Host "ERROR: No yaml flows found in $FlowRoot"
    exit 1
}

$IncludeTagArg = if ([string]::IsNullOrWhiteSpace($IncludeTag)) { "__EMPTY__" } else { $IncludeTag }
$MaestroCmdArg = if ([string]::IsNullOrWhiteSpace($MaestroCmd)) { "maestro" } else { $MaestroCmd }

$overallFailed = $false
$retryRows = @()

foreach ($flow in $flowFiles) {
    $attempt1 = Run-FlowBatch -RepoRoot $RepoRoot -Suite $Suite -Flow $flow -Devices $devices -AppId $AppId -ClearState $ClearState -MaestroCmdArg $MaestroCmdArg -IncludeTagArg $IncludeTagArg
    $failed = @($attempt1 | Where-Object { -not $_.Passed })

    if ($failed.Count -gt 0 -and $RetryCount -gt 0) {
        Write-Section "Retrying failed pairs for $($flow.BaseName)"
        foreach ($row in $failed) {
            Write-Host ("Retry -> Flow {0} on Device {1}" -f $row.Flow, $row.Device)
            $retryResult = Run-FlowBatch -RepoRoot $RepoRoot -Suite $Suite -Flow $flow -Devices @($row.Device) -AppId $AppId -ClearState $ClearState -MaestroCmdArg $MaestroCmdArg -IncludeTagArg $IncludeTagArg
            $retryRows += $retryResult | ForEach-Object {
                [pscustomobject]@{
                    flow = $_.Flow
                    device = $_.Device
                    retry_exit_code = $_.ExitCode
                    retry_artifacts_ok = $_.ArtifactsOk
                    retry_passed = $_.Passed
                    log_file = $_.LogFile
                }
            }
        }
    }

    $postRows = @()
    foreach ($device in $devices) {
        $safeFlow = $flow.BaseName.Replace(' ', '_')
        $safeDevice = $device.Replace(' ', '_')
        $resultFile = Join-Path $ResultsDir ("{0}_{1}.csv" -f $safeFlow, $safeDevice)
        if (Test-Path -LiteralPath $resultFile) {
            try {
                $postRows += Import-Csv -LiteralPath $resultFile
            } catch {}
        }
    }

    $flowFailed = @($postRows | Where-Object { $_.status -ne 'PASS' }).Count -gt 0
    if ($flowFailed) {
        $overallFailed = $true
        Write-Host "Flow $($flow.BaseName) failed on one or more devices after retry"
    } else {
        Write-Host "Flow $($flow.BaseName) completed successfully on all devices"
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
