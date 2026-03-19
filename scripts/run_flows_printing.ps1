$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

adb devices
maestro devices

$devices = adb devices | Select-Object -Skip 1 | ForEach-Object {
    $parts = ($_ -replace "`r","") -split "\s+"
    if ($parts.Length -ge 2 -and $parts[1] -eq "device") { $parts[0] }
}

if (-not $devices) { exit 1 }

$flows = @(
    "Printing Flow\flow1.yaml",
    "Printing Flow\flow2.yaml"
)

foreach ($flow in $flows) {
    foreach ($device in $devices) {
        & maestro test -d $device $flow
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
}

exit 0
