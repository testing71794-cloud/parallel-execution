param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$Suite,
    [Parameter(Mandatory=$true)][string]$FlowDir,
    [string]$IncludeTag = "",
    [string]$AppId = "",
    [string]$ClearState = "true"
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

    $jobs = @()

    foreach ($device in $devices) {
        $jobs += Start-Job -Name "$flowName-$device" -ArgumentList @(
            $RunnerBat, $Suite, $flowPath, $flowName, $device, $AppId, $ClearState, $IncludeTag
        ) -ScriptBlock {
            param($RunnerBat, $Suite, $flowPath, $flowName, $device, $AppId, $ClearState, $IncludeTag)

            Set-Location (Split-Path -Parent (Split-Path -Parent $RunnerBat))

            & $RunnerBat $Suite $flowPath $flowName $device $AppId $ClearState $IncludeTag

            [pscustomobject]@{
                Flow = $flowName
                Device = $device
                ExitCode = $LASTEXITCODE
            }
        }
    }

    Wait-Job -Job $jobs | Out-Null

    $flowFailed = $false

    foreach ($job in $jobs) {
        $result = Receive-Job -Job $job
        if ($null -eq $result) {
            Write-Host "No result returned from job $($job.Name)"
            $flowFailed = $true
            $overallFailed = $true
        } else {
            foreach ($item in @($result)) {
                if ($item.PSObject.Properties.Name -contains 'Device') {
                    Write-Host ("Device {0} -> ExitCode {1}" -f $item.Device, $item.ExitCode)
                    if ([int]$item.ExitCode -ne 0) {
                        $flowFailed = $true
                        $overallFailed = $true
                    }
                } else {
                    $text = [string]$item
                    if ($text.Trim().Length -gt 0) { Write-Host $text }
                }
            }
        }

        if ($job.State -ne "Completed") {
            $flowFailed = $true
            $overallFailed = $true
        }

        Remove-Job -Job $job -Force | Out-Null
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
