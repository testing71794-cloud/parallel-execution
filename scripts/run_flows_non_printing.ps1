\
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$adb = "C:\Users\HP\AppData\Local\Android\Sdk\platform-tools\adb.exe"

if (!(Test-Path $adb)) {
    Write-Host "ADB not found at: $adb"
    exit 1
}

Write-Host "===== ADB DEVICES ====="
& $adb devices

Write-Host "===== MAESTRO DEVICES ====="
maestro devices

$devices = & $adb devices | Select-Object -Skip 1 | ForEach-Object {
    $parts = ($_ -replace "`r","") -split "\s+"
    if ($parts.Length -ge 2 -and $parts[1] -eq "device") { $parts[0] }
}

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

foreach ($flow in $flows) {
    if (!(Test-Path $flow)) {
        Write-Host "Flow not found: $flow"
        exit 1
    }

    Write-Host ""
    Write-Host "======================================="
    Write-Host "Running $flow on all devices"
    Write-Host "======================================="

    foreach ($device in $devices) {
        $safeFlow = [System.IO.Path]::GetFileNameWithoutExtension($flow)
        $logFile = "reports\nonprinting\${safeFlow}_$device.log"
        $xmlFile = "reports\nonprinting\${safeFlow}_$device.xml"

        Write-Host "Running on device: $device"

        & maestro test -d $device $flow --format junit --output $xmlFile *>&1 | Tee-Object -FilePath $logFile

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed on device $device for flow $flow"
            exit 1
        }
    }

    Write-Host "Completed $flow on all devices"
}

$files = Get-ChildItem "reports\nonprinting\*.xml" -ErrorAction SilentlyContinue
if (-not $files) {
    Write-Host "No test reports generated!"
    exit 1
}

Write-Host "All non-printing flows completed successfully."
exit 0
