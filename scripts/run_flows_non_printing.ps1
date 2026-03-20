$ErrorActionPreference = "Stop"

# Move to project root
Set-Location "$PSScriptRoot\.."

# ADB path (keep as is)
$adb = "C:\Users\HP\AppData\Local\Android\Sdk\platform-tools\adb.exe"

if (!(Test-Path $adb)) {
    Write-Host "ADB not found at: $adb"
    exit 1
}

Write-Host "===== ADB DEVICES ====="
& $adb devices

# Get connected devices
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

# Flow list
$flows = @(
    "Non printing flows\flow1.yaml",
    "Non printing flows\flow2.yaml",
    "Non printing flows\flow3.yaml",
    "Non printing flows\flow4.yaml",
    "Non printing flows\flow5.yaml",
    "Non printing flows\flow6.yaml",
    "Non printing flows\flow7.yaml"
)

# Create report directory
New-Item -ItemType Directory -Force -Path "reports\nonprinting" | Out-Null

$projectRoot = (Get-Location).Path
$hadFailure = $false
$failedItems = @()

# Loop flows
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
        $logFile = "reports\nonprinting\${safeFlow}_$device.log"
        $xmlFile = "reports\nonprinting\${safeFlow}_$device.xml"

        Write-Host "Starting on device: $device"

        $job = Start-Job -ArgumentList $projectRoot, $flow, $device, $xmlFile, $logFile, $adb -ScriptBlock {
            param($rootPath, $flowFile, $deviceId, $xmlOut, $logOut, $adbPath)

            try {
                Set-Location $rootPath

                # Bind device
                $env:ANDROID_SERIAL = $deviceId

                Write-Host "=================================="
                Write-Host "Running flow: $flowFile"
                Write-Host "On device: $deviceId"
                Write-Host "=================================="

                # Verify correct device
                & $adbPath -s $deviceId shell getprop ro.product.model

                # 🔥 IMPORTANT FIX (device binding)
                & maestro --device $deviceId test $flowFile --format junit --output $xmlOut *>&1 | Tee-Object -FilePath $logOut

                $exitCode = $LASTEXITCODE
            }
            catch {
                Write-Host "Error running flow $flowFile on $deviceId"
                $exitCode = 1
            }

            [PSCustomObject]@{
                Device = $deviceId
                Flow = $flowFile
                ExitCode = $exitCode
                Xml = $xmlOut
                Log = $logOut
            }
        }

        $jobs += $job
    }

    # Wait for all devices
    Wait-Job -Job $jobs | Out-Null

    # Collect results
    foreach ($job in $jobs) {
        $result = Receive-Job -Job $job

        if ($null -eq $result) {
            $hadFailure = $true
            $failedItems += "$flow :: UNKNOWN_JOB_FAILURE"
        }
        elseif ($result.ExitCode -ne 0) {
            Write-Host "❌ Failed on device $($result.Device) for flow $($result.Flow)"
            $hadFailure = $true
            $failedItems += "$($result.Flow) :: $($result.Device)"
        }
        else {
            Write-Host "✅ Passed on device $($result.Device) for flow $($result.Flow)"
        }
    }

    # Cleanup
    $jobs | Remove-Job -Force

    Write-Host "Completed $flow on all devices"
}

# Check reports
$files = Get-ChildItem "reports\nonprinting\*.xml" -ErrorAction SilentlyContinue

if (-not $files) {
    Write-Host "No test reports generated!"
    $hadFailure = $true
    $failedItems += "REPORTS :: NON_PRINTING :: NONE_GENERATED"
}

# Final result
if ($hadFailure) {
    Write-Host ""
    Write-Host "================ FAILED FLOWS ================"
    $failedItems | ForEach-Object { Write-Host $_ }
    exit 1
}

Write-Host ""
Write-Host "==========================================="
Write-Host "🎉 All non-printing flows completed successfully"
Write-Host "==========================================="

exit 0