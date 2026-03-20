$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$adb = "C:\Users\HP\AppData\Local\Android\Sdk\platform-tools\adb.exe"

if (!(Test-Path $adb)) {
    Write-Host "ADB not found at: $adb"
    exit 1
}

Write-Host "===== ADB DEVICES ====="
& $adb devices

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
    "Printing Flow\flow1.yaml",
    "Printing Flow\flow2.yaml",
    "Printing Flow\flow3.yaml",
    "Printing Flow\flow4.yaml",
    "Printing Flow\flow5.yaml",
    "Printing Flow\flow6.yaml",
    "Printing Flow\flow7.yaml",
    "Printing Flow\flow8.yaml",
    "Printing Flow\flow9.yaml",
    "Printing Flow\flow10.yaml",
    "Printing Flow\flow11.yaml"
)

New-Item -ItemType Directory -Force -Path "reports\printing" | Out-Null

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

    $jobs = @()

    foreach ($device in $devices) {
        $safeFlow = [System.IO.Path]::GetFileNameWithoutExtension($flow)
        $logFile = "reports\printing\${safeFlow}_$device.log"
        $xmlFile = "reports\printing\${safeFlow}_$device.xml"

        Write-Host "Starting on device: $device"

        $job = Start-Job -ArgumentList $projectRoot, $flow, $device, $xmlFile, $logFile, $adb -ScriptBlock {
            param($rootPath, $flowFile, $deviceId, $xmlOut, $logOut, $adbPath)

            Set-Location $rootPath
            $env:ANDROID_SERIAL = $deviceId

            Write-Host "Running flow $flowFile on device $deviceId"
            & $adbPath -s $deviceId shell getprop ro.product.model

            & maestro --device $deviceId test $flowFile --format junit --output $xmlOut *>&1 | Tee-Object -FilePath $logOut

            [PSCustomObject]@{
                Device = $deviceId
                Flow = $flowFile
                ExitCode = $LASTEXITCODE
                Xml = $xmlOut
                Log = $logOut
            }
        }

        $jobs += $job
    }

    Wait-Job -Job $jobs | Out-Null

    foreach ($job in $jobs) {
        $result = Receive-Job -Job $job
        if ($null -eq $result) {
            $hadFailure = $true
            $failedItems += "$flow :: UNKNOWN_JOB_FAILURE"
        } elseif ($result.ExitCode -ne 0) {
            Write-Host "Failed on device $($result.Device) for flow $($result.Flow)"
            $hadFailure = $true
            $failedItems += "$($result.Flow) :: $($result.Device)"
        } else {
            Write-Host "Passed on device $($result.Device) for flow $($result.Flow)"
        }
    }

    $jobs | Remove-Job -Force
    Write-Host "Completed $flow on all devices"
}

$files = Get-ChildItem "reports\printing\*.xml" -ErrorAction SilentlyContinue
if (-not $files) {
    Write-Host "No test reports generated!"
    $hadFailure = $true
    $failedItems += "REPORTS :: PRINTING :: NONE_GENERATED"
}

if ($hadFailure) {
    Write-Host ""
    Write-Host "================ FAILED FLOWS ================"
    $failedItems | ForEach-Object { Write-Host $_ }
    exit 1
}

Write-Host "All printing flows completed successfully."
exit 0