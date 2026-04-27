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

function Add-AdbFromEnvToPath {
    if ([string]::IsNullOrWhiteSpace($env:ADB_HOME)) { return }
    $d = $env:ADB_HOME.Trim()
    if (-not (Test-Path -LiteralPath (Join-Path $d "adb.exe"))) { return }
    $parts = @()
    if ($env:Path) { $parts = $env:Path -split ';' }
    if ($parts -contains $d -or $parts -contains $d.TrimEnd('\')) { return }
    $env:Path = $d + ";" + $env:Path
}

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

    if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
        throw "adb not on PATH. Set ADB_HOME / ANDROID_HOME (platform-tools) in Jenkins, or use scripts that call set_maestro_java.bat."
    }
    $adbOutput = & adb devices
    if ($LASTEXITCODE -ne 0) { throw "adb devices failed" }

    foreach ($line in $adbOutput) {
        if ($line -match '^(?<id>\S+)\s+device$') { $devices += $matches['id'] }
    }
    return $devices | Select-Object -Unique
}

function Disable-AutofillForDevice([string]$DeviceId) {
    $original = "unknown"
    try {
        $raw = & adb -s $DeviceId shell settings get secure autofill_service 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($raw)) {
            $original = ($raw | Select-Object -First 1).ToString().Trim()
        }
    } catch {
        Write-Host "[WARN] Device $DeviceId - failed reading autofill_service: $($_.Exception.Message)"
    }

    Write-Host "[INFO] Device $DeviceId - autofill_service before change: $original"

    try {
        & adb -s $DeviceId shell settings put secure autofill_service null 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[INFO] Device $DeviceId - autofill disabled (autofill_service=null)"
        } else {
            Write-Host "[WARN] Device $DeviceId - could not disable autofill_service, continuing"
        }
    } catch {
        Write-Host "[WARN] Device $DeviceId - autofill disable command failed: $($_.Exception.Message)"
    }

    foreach ($pkg in @("com.samsung.android.samsungpassautofill", "com.samsung.android.authfw")) {
        try {
            & adb -s $DeviceId shell cmd package disable-user --user 0 $pkg 1>$null 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[INFO] Device $DeviceId - Samsung package disabled: $pkg"
            } else {
                Write-Host "[WARN] Device $DeviceId - Samsung package not disabled/supported: $pkg"
            }
        } catch {
            Write-Host "[WARN] Device $DeviceId - Samsung package disable failed ($pkg): $($_.Exception.Message)"
        }
    }

    return $original
}

function Restore-AutofillForDevice([string]$DeviceId, [string]$OriginalService) {
    if ([string]::IsNullOrWhiteSpace($OriginalService) -or $OriginalService -eq "unknown") {
        Write-Host "[WARN] Device $DeviceId - no original autofill_service captured; skip restore"
        return
    }
    try {
        & adb -s $DeviceId shell settings put secure autofill_service $OriginalService 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[INFO] Device $DeviceId - autofill_service restored to $OriginalService"
        } else {
            Write-Host "[WARN] Device $DeviceId - failed to restore autofill_service"
        }
    } catch {
        Write-Host "[WARN] Device $DeviceId - autofill restore failed: $($_.Exception.Message)"
    }
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
    Write-Host "Maestro output streams to (tail for live progress): $batchLog"
    Write-Host "This step can run many minutes; the Jenkins console stays quiet until Maestro exits."

    # --device is global: before `test` (https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options)
    $args = @(
        "--device", $deviceList,
        "test",
        "--shard-all", $shardCount.ToString()
    )
    if (-not [string]::IsNullOrWhiteSpace($IncludeTag)) {
        $args += @("--include-tags", $IncludeTag)
    }
    $args += @($flowPath)
    $configPath = Join-Path $RepoRoot "config.yaml"
    if (Test-Path -LiteralPath $configPath) {
        $args += @("--config", $configPath)
    }

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

    # Use cmd redirection directly so Java warnings on stderr are captured in log,
    # not treated by PowerShell as a terminating NativeCommandError.
    $cmdLine = "$MaestroCmd $argsString >> " + (Quote-Arg $batchLog) + " 2>>&1"
    cmd.exe /d /c $cmdLine
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and (Test-Path -LiteralPath $batchLog)) {
        Write-Host "[INFO] Maestro failed (exit $exitCode). Last 50 lines of $batchLog :"
        Get-Content -LiteralPath $batchLog -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
    }

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

Add-AdbFromEnvToPath
$devices = Read-DeviceIds -RepoRoot $RepoRoot
try {
    if (Get-Command adb -ErrorAction SilentlyContinue) {
        $null = & adb start-server 2>&1
    } else {
        Write-Host "[WARN] adb not on PATH after ADB_HOME; skipping start-server. Set ANDROID_HOME / ADB in Jenkins if needed."
    }
} catch {
    Write-Host "[WARN] adb start-server: $($_.Exception.Message)"
}
$restoreAutofill = ($env:AUTOFILL_RESTORE_AFTER_TEST -match '^(?i:1|true|yes|on)$')
$deviceAutofillState = @{}
Write-Host ""
Write-Host "Devices found: $($devices.Count)"
foreach ($d in $devices) { Write-Host " - $d" }
if ($devices.Count -eq 0) { Write-Host "ERROR: No connected devices found"; exit 1 }

Write-Section "Disabling Android autofill/password-save prompts (best-effort)"
foreach ($d in $devices) {
    $deviceAutofillState[$d] = Disable-AutofillForDevice -DeviceId $d
}

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

if ($restoreAutofill) {
    Write-Section "Restoring Android autofill service (best-effort)"
    foreach ($d in $devices) {
        $orig = if ($deviceAutofillState.ContainsKey($d)) { [string]$deviceAutofillState[$d] } else { "unknown" }
        Restore-AutofillForDevice -DeviceId $d -OriginalService $orig
    }
}

if ($overallFailed) { exit 1 } else { exit 0 }
