param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$Suite,
    [Parameter(Mandatory = $true)][string]$FlowDir,
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
    # Required: use MAESTRO_HOME\maestro.bat|maestro.cmd (per Jenkins: do not depend on bare maestro in PATH)
    if ([string]::IsNullOrWhiteSpace($env:MAESTRO_HOME)) {
        throw "MAESTRO_HOME is not set. Set the Jenkins `MAESTRO_HOME` parameter to the folder that contains `maestro.bat`."
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
        throw "adb not on PATH. Set ANDROID_HOME/ADB_HOME so platform-tools\adb is available."
    }
    $raw = & adb devices
    if ($LASTEXITCODE -ne 0) { throw "adb devices failed (exit $LASTEXITCODE)" }
    foreach ($line in $raw) {
        if ($line -match '^(?<s>\S+)\s+device\s*$') { $out.Add($matches['s'].Trim()) }
    }
    return $out
}

function Read-DetectedFileSerials([string]$RepoRoot) {
    $detected = Join-Path $RepoRoot "detected_devices.txt"
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
        throw "No Android devices in state 'device' (authorized + ready). Remove or authorize unauthorized devices, fix offline, and reconnect USB."
    }
    $fileSerials = [array](Read-DetectedFileSerials -RepoRoot $RepoRoot)
    if ($fileSerials.Count -eq 0) {
        return $authorized
    }
    $picked = @()
    foreach ($s in $fileSerials) { if ($authorized -contains $s) { $picked += $s } }
    if ($picked.Count -eq 0) {
        throw "detected_devices.txt has no serials that are currently authorized+device in 'adb devices'. Re-run device detection; remove unauthorized or offline."
    }
    if ($picked.Count -lt $fileSerials.Count) {
        $missing = $fileSerials | Where-Object { $picked -notcontains $_ }
        Write-Host "[WARN] Dropping device serial(s) not in authorized state: $($missing -join ', ')" 
    }
    return $picked
}

function Start-RunOneOnDevice {
    param(
        [string]$RepoRoot,
        [string]$Suite,
        [string]$FlowPath,
        [string]$DeviceId,
        [string]$AppId,
        [string]$ClearState,
        [string]$MaestroPath,
        [string]$TagOrEmpty
    )
    $runOne = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "scripts\run_one_flow_on_device.bat"))
    $t = if ([string]::IsNullOrWhiteSpace($TagOrEmpty)) { "__EMPTY__" } else { $TagOrEmpty }
    $cmd = "call {0} {1} {2} {3} {4} {5} {6} {7}" -f @(
        (Quote-Arg $runOne),
        (Quote-Arg $Suite),
        (Quote-Arg $FlowPath),
        (Quote-Arg $DeviceId),
        (Quote-Arg $AppId),
        (Quote-Arg $ClearState),
        (Quote-Arg $MaestroPath),
        (Quote-Arg $t)
    )
    $full = "cd /d " + (Quote-Arg $RepoRoot) + " && " + $cmd
    return Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $full) -NoNewWindow -PassThru
}

function Invoke-ParallelRunOne {
    param(
        [string]$RepoRoot,
        [string]$Suite,
        [System.IO.FileInfo]$flow,
        [string[]]$devices,
        [string]$AppId,
        [string]$ClearState,
        [string]$maestroLaunch,
        [string]$IncludeTag
    )
    $fn = $flow.BaseName
    $pList = [System.Collections.ArrayList]::new()
    foreach ($dev in $devices) {
        $p = Start-RunOneOnDevice -RepoRoot $RepoRoot -Suite $Suite -FlowPath $flow.FullName -DeviceId $dev -AppId $AppId -ClearState $ClearState -MaestroPath $maestroLaunch -TagOrEmpty $IncludeTag
        [void]$pList.Add($p)
        Write-Host "Launched run_one (PID=$($p.Id)) device=$dev  -> per-device log/CSV under reports\$Suite\ (e.g. logs\${fn}_$($dev -replace '[^\w\-\.]', '_').log)" 
    }
    return $pList
}

function Wait-ParallelWithHeartbeat {
    param(
        [System.Collections.ArrayList]$Processes,
        [string[]]$Devices,
        [string]$FlowName,
        [string]$Suite,
        [string]$ReportsDir,
        [int]$HeartbeatSeconds = 10
    )
    $safeFlow = $FlowName.Replace(' ', '_')
    while ($true) {
        $running = @($Processes | Where-Object { -not $_.HasExited })
        if ($running.Count -eq 0) { break }
        Write-Host "[HEARTBEAT] flow=$FlowName running_procs=$($running.Count) elapsed=$(Get-Date -Format 'HH:mm:ss')"
        for ($i = 0; $i -lt $Devices.Count; $i++) {
            $dev = $Devices[$i]
            $p = $Processes[$i]
            $safeDev = $dev.Replace(' ', '_')
            $logFile = Join-Path (Join-Path $ReportsDir "logs") ("{0}_{1}.log" -f $safeFlow, $safeDev)
            $state = if ($p.HasExited) { "EXIT:$($p.ExitCode)" } else { "RUN" }
            $lastLine = ""
            if (Test-Path -LiteralPath $logFile) {
                try {
                    $tail = Get-Content -LiteralPath $logFile -Tail 1 -ErrorAction Stop
                    if ($null -ne $tail) {
                        # Get-Content may return a scalar string for single-line output.
                        # Accessing [0] on a scalar string yields a char, which has no Trim().
                        $lineObj = @($tail)[0]
                        $lastLine = ([string]$lineObj).Trim()
                    }
                } catch {
                    # run_one appends logs concurrently; temporary sharing violations are expected.
                    $lastLine = "(log temporarily locked)"
                }
            }
            if ([string]::IsNullOrWhiteSpace($lastLine)) { $lastLine = "(no log line yet)" }
            Write-Host ("  - {0} {1} :: {2}" -f $dev, $state, $lastLine)
        }
        Start-Sleep -Seconds $HeartbeatSeconds
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

Write-Section "RUN SUITE SAME MACHINE (PARALLEL PER DEVICE, ONE ADB, MAESTRO PER SERIAL)"
Write-Host "Repo root: $RepoRoot"
Write-Host "Flow root: $FlowRoot"
Write-Host "Include tag: $IncludeTag"
Write-Host "Retry count: $RetryCount"

if ([string]::IsNullOrWhiteSpace($AppId)) { Write-Host "ERROR: AppId (APP_PACKAGE) is required"; exit 1 }
if ([string]::IsNullOrWhiteSpace($ClearState)) { $ClearState = "true" }
if ([string]::IsNullOrWhiteSpace($MaestroCmd)) { $MaestroCmd = "maestro" }

if (-not (Test-Path -LiteralPath $FlowRoot)) { Write-Host "ERROR: Flow directory not found: $FlowRoot"; exit 1 }

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "status") | Out-Null

# --- Single ADB warm (no kill-server, no per-device start-server) ---
Add-AdbFromEnvToPath
$null = cmd /c "adb start-server 2>nul"
$null = cmd /c "adb devices 1>nul 2>nul"
Start-Sleep -Seconds 2
Write-Host "[INFO] ADB is ready. Further adb traffic is in run_one_flow (autofill) and Maestro only, not ADB server restarts here."

try {
    $devices = [array](Merge-AndPickDevices -RepoRoot $RepoRoot)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
Write-Host ""
Write-Host "Authorized 'device' serials for this run: $($devices.Count)"
foreach ($d in $devices) { Write-Host "  - $d" }

$maestroLaunch = $null
try { $maestroLaunch = Resolve-MaestroLauncherPath } catch { Write-Host "ERROR: $($_.Exception.Message)"; exit 1 }
Write-Host "Maestro launcher: $maestroLaunch"

$flowFiles = Get-ChildItem -LiteralPath $FlowRoot -Filter *.yaml -File | Sort-Object Name
if (-not $flowFiles -or $flowFiles.Count -eq 0) { Write-Host "ERROR: No yaml flows found in $FlowRoot"; exit 1 }

$overallFailed = $false
$retryRows = [System.Collections.ArrayList]::new()

foreach ($flow in $flowFiles) {
    $flowName = $flow.BaseName
    Write-Section "Running $flowName on all devices in parallel (run_one_flow on each serial)"
    foreach ($d in $devices) { Write-Host "  device $d" }

    $pList = Invoke-ParallelRunOne -RepoRoot $RepoRoot -Suite $Suite -flow $flow -devices $devices -AppId $AppId -ClearState $ClearState -maestroLaunch $maestroLaunch -IncludeTag $IncludeTag
    Wait-ParallelWithHeartbeat -Processes $pList -Devices $devices -FlowName $flowName -Suite $Suite -ReportsDir $ReportsDir
    $batchCode = 0
    foreach ($px in $pList) {
        $ex = if ($null -ne $px.ExitCode) { [int]$px.ExitCode } else { 1 }
        if ($ex -ne 0) { $batchCode = 1 }
    }
    if ($batchCode -ne 0) {
        Write-Host "[INFO] $flowName had at least one device failure. Exit code batch=$batchCode"
    }

    if ($batchCode -ne 0 -and $RetryCount -gt 0) {
        Write-Section "Retry: $flowName (same devices, another parallel batch)"
        $p2 = Invoke-ParallelRunOne -RepoRoot $RepoRoot -Suite $Suite -flow $flow -devices $devices -AppId $AppId -ClearState $ClearState -maestroLaunch $maestroLaunch -IncludeTag $IncludeTag
        Wait-ParallelWithHeartbeat -Processes $p2 -Devices $devices -FlowName $flowName -Suite $Suite -ReportsDir $ReportsDir
        $r2 = 0
        foreach ($px in $p2) {
            $ex = if ($null -ne $px.ExitCode) { [int]$px.ExitCode } else { 1 }
            if ($ex -ne 0) { $r2 = 1 }
        }
        [void]$retryRows.Add([pscustomobject]@{ flow = $flowName; retry_batch_exit = $r2; devices = ($devices -join ',') })
        if ($r2 -ne 0) { $overallFailed = $true; Write-Host "Flow $flowName still failed after retry" }
        else { Write-Host "Flow $flowName passed after retry" }
    } elseif ($batchCode -ne 0) {
        $overallFailed = $true
        Write-Host "Flow $flowName failed (no retry)"
    } else {
        Write-Host "Flow $flowName all devices passed"
    }
}

# ---- Merge CSVs produced by run_one (one file per flow+device) ----
Write-Section "Merging result files"
$tempCsvs = Get-ChildItem -LiteralPath $ResultsDir -Filter *.csv -File | Where-Object { $_.Name -notin @('all_results.csv', 'device_summary.csv', 'retry_summary.csv') } | Sort-Object Name
if (-not $tempCsvs -or $tempCsvs.Count -eq 0) { Write-Host "ERROR: No result CSV files in $ResultsDir (run_one should have written)."; exit 1 }

"suite,flow,device,status,exit_code,reason,log_file" | Set-Content -Path $MasterCsv -Encoding Ascii
foreach ($csv in $tempCsvs) {
    $ln = Get-Content -LiteralPath $csv.FullName
    if ($ln.Count -gt 1) { $ln | Select-Object -Skip 1 | ForEach-Object { if ($null -ne $_ -and $_ -match '\S') { Add-Content -Path $MasterCsv -Value $_ } } }
}

try {
    $rows = Import-Csv -LiteralPath $MasterCsv
    $summary = $rows | Group-Object device | ForEach-Object {
        $deviceRows = $_.Group
        $passCount = @($deviceRows | Where-Object { $_.status -eq 'PASS' -or $_.status -eq 'FLAKY' }).Count
        $failCount = @($deviceRows | Where-Object { $_.status -ne 'PASS' -and $_.status -ne 'FLAKY' }).Count
        if ($passCount -eq 0) { $passCount = @($deviceRows | Where-Object { $_.status -like '*PASS*' -or $_.status -like '*FLAKY*' }).Count }
        if ($failCount -eq 0) { $failCount = $deviceRows.Count - $passCount }
        [pscustomobject]@{
            device = $_.Name
            total_flows = $deviceRows.Count
            passed     = $passCount
            failed     = $failCount
            overall_status = $(if ($failCount -gt 0) { 'FAIL' } else { 'PASS' })
        }
    } | Sort-Object device
    $summary | Export-Csv -LiteralPath $DeviceSummaryCsv -NoTypeInformation
} catch {
    Write-Host "[WARN] Device summary from merged CSV: $($_.Exception.Message)"
}
if ($retryRows.Count -gt 0) {
    $retryRows | Export-Csv -LiteralPath $RetryCsv -NoTypeInformation
    Write-Host "Retry summary: $RetryCsv"
}
Write-Host "Merged: $MasterCsv"

if ($overallFailed) { exit 1 } else { exit 0 }
