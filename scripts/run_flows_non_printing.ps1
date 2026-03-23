$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

function Get-AdbPath {
    if ($env:ADB_PATH -and (Test-Path $env:ADB_PATH)) { return $env:ADB_PATH }
    if ($env:ANDROID_HOME) {
        $candidate = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    if ($env:ANDROID_SDK_ROOT) {
        $candidate = Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "ADB not found. Set ADB_PATH or add adb to PATH."
}

function Get-MaestroPath {
    $candidate = Join-Path $env:USERPROFILE ".maestro\bin\maestro.cmd"
    if (Test-Path $candidate) { return $candidate }
    $cmd = Get-Command maestro -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Maestro not found. Install Maestro or add it to PATH."
}

$adb = Get-AdbPath
$maestro = Get-MaestroPath
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { throw "Python not found in PATH." }

Write-Host "===== ADB DEVICES ====="
& $adb devices

$devices = & $adb devices | Select-Object -Skip 1 | ForEach-Object {
    $parts = ($_ -replace "`r","") -split "\s+"
    if ($parts.Length -ge 2 -and $parts[1] -eq "device") { $parts[0] }
} | Where-Object { $_ -and $_.Trim() -ne "" }

if (-not $devices -or $devices.Count -eq 0) {
    Write-Host "No connected Android devices found."
    exit 1
}

Write-Host "Connected devices:"
$devices | ForEach-Object { Write-Host " - $_" }

$flows = @(
    "Non printing flows\flow1.yaml",
    "Non printing flows\flow2.yaml",
    "Non printing flows\flow3.yaml",
    "Non printing flows\flow4.yaml",
    "Non printing flows\flow5.yaml",
    "Non printing flows\flow6.yaml",
    "Non printing flows\flow7.yaml"
)

# Same layout as run_all_flows_pipeline.bat + update_excel_after_flow.py
$resultsDir = "reports\raw\nonprinting"
$excelDir = "reports\excel"
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $excelDir | Out-Null

$projectRoot = (Get-Location).Path
$hadFailure = $false
$failedItems = @()

for ($index = 0; $index -lt $flows.Count; $index++) {
    $flow = $flows[$index]

    if (!(Test-Path $flow)) {
        Write-Host "Flow not found: $flow"
        $hadFailure = $true
        $failedItems += "$flow :: FILE_NOT_FOUND"
        continue
    }

    $safeFlow = [System.IO.Path]::GetFileNameWithoutExtension($flow)

    Write-Host ""
    Write-Host "========================================================="
    Write-Host "Running $flow on all devices in parallel"
    Write-Host "========================================================="

    $running = @()

    foreach ($device in $devices) {
        $logFile = Join-Path $projectRoot "$resultsDir\${safeFlow}_$device.log"
        $xmlFile = Join-Path $projectRoot "$resultsDir\${safeFlow}_$device.xml"
        $debugDir = Join-Path $projectRoot "$resultsDir\debug_${safeFlow}_$device"
        $runnerFile = Join-Path $projectRoot "$resultsDir\runner_${safeFlow}_$device.ps1"

        New-Item -ItemType Directory -Force -Path $debugDir | Out-Null

        Write-Host "Starting on device: $device"
        & $adb -s $device shell getprop ro.product.model

        $runnerScript = @"
Set-Location '$projectRoot'
`$env:ANDROID_SERIAL = '$device'

# Official CLI: global --device before `test` — https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options
& '$maestro' --device $device test '$flow' --format junit --output '$xmlFile' --debug-output '$debugDir' *>> '$logFile'
exit `$LASTEXITCODE
"@
        Set-Content -Path $runnerFile -Value $runnerScript -Encoding UTF8

        $proc = Start-Process powershell.exe `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runnerFile`"" `
            -PassThru `
            -WindowStyle Hidden

        $running += [PSCustomObject]@{
            Device = $device
            Flow = $flow
            Process = $proc
            Xml = $xmlFile
            Log = $logFile
            Runner = $runnerFile
        }
    }

    foreach ($item in $running) {
        $item.Process.WaitForExit()

        if ($item.Process.ExitCode -ne 0) {
            Write-Host "Failed on device $($item.Device) for flow $($item.Flow)"
            $hadFailure = $true
            $failedItems += "$($item.Flow) :: $($item.Device)"
        } else {
            Write-Host "Passed on device $($item.Device) for flow $($item.Flow)"
        }

        if (Test-Path $item.Runner) {
            Remove-Item $item.Runner -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "Updating Excel after $flow (all devices)"
    $flowArg = "${safeFlow}.yaml"
    if ($python -eq "py") {
        & py -3 scripts\update_excel_after_flow.py --flow $flowArg --type nonprinting
    } else {
        & python scripts\update_excel_after_flow.py --flow $flowArg --type nonprinting
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Excel update failed for $flow"
        $hadFailure = $true
        $failedItems += "$flow :: EXCEL_UPDATE_FAILED"
    }

    Write-Host "Completed $flow on all devices"
}

$files = Get-ChildItem "$resultsDir\*.xml" -ErrorAction SilentlyContinue
if (-not $files) {
    Write-Host "No test reports generated!"
    $hadFailure = $true
    $failedItems += "REPORTS :: NON_PRINTING :: NONE_GENERATED"
}

if ($hadFailure) {
    Write-Host ""
    Write-Host "================ FAILED FLOWS ================"
    $failedItems | ForEach-Object { Write-Host $_ }
    exit 1
}

Write-Host "All non-printing flows completed successfully."
exit 0
