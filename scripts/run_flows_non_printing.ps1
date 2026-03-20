$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$adb = "C:\Users\HP\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$maestro = "$env:USERPROFILE\.maestro\bin\maestro.cmd"

if (!(Test-Path $adb)) {
    Write-Host "ADB not found at: $adb"
    exit 1
}

if (!(Test-Path $maestro)) {
    $maestro = "maestro"
}

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

New-Item -ItemType Directory -Force -Path "reports\nonprinting" | Out-Null

$projectRoot = (Get-Location).Path
$hadFailure = $false
$failedItems = @()

foreach ($flow in $flows) {

    if (!(Test-Path $flow)) {
        Write-Host "Flow not found: $flow"
        $hadFailure = $true
        $failedItems += "$flow :: FILE_NOT_FOUND"
        continue
    }

    Write-Host ""
    Write-Host "======================================="
    Write-Host "Running $flow on all devices in parallel"
    Write-Host "======================================="

    $running = @()

    foreach ($device in $devices) {
        $safeFlow = [System.IO.Path]::GetFileNameWithoutExtension($flow)
        $logFile = Join-Path $projectRoot "reports\nonprinting\${safeFlow}_$device.log"
        $xmlFile = Join-Path $projectRoot "reports\nonprinting\${safeFlow}_$device.xml"
        $debugDir = Join-Path $projectRoot "reports\nonprinting\debug_${safeFlow}_$device"
        $runnerFile = Join-Path $projectRoot "reports\nonprinting\runner_${safeFlow}_$device.ps1"

        New-Item -ItemType Directory -Force -Path $debugDir | Out-Null

        Write-Host "Starting on device: $device"
        & $adb -s $device shell getprop ro.product.model

        $runnerScript = @"
Set-Location '$projectRoot'
`$env:ANDROID_SERIAL = '$device'

& '$maestro' --device='$device' test '$flow' --format junit --output '$xmlFile' --debug-output '$debugDir' *>> '$logFile'
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

    Write-Host "Completed $flow on all devices"
}

$files = Get-ChildItem "reports\nonprinting\*.xml" -ErrorAction SilentlyContinue
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