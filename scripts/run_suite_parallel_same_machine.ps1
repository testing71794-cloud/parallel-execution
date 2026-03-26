param(
    [string]$Suite,
    [string]$FlowDir,
    [string]$IncludeTag,
    [string]$AppId,
    [string]$ClearState
)

$devices = adb devices | Select-String "device$" | ForEach-Object {
    ($_ -split "\s+")[0]
}

foreach ($flow in Get-ChildItem $FlowDir -Filter *.yaml) {
    $jobs = @()

    foreach ($device in $devices) {
        $jobs += Start-Job -ScriptBlock {
            param($flowPath, $flowName, $device)

            cmd /c "scripts\run_one_flow_on_device.bat nonprinting `"$flowPath`" `"$flowName`" `"$device`""
        } -ArgumentList $flow.FullName, $flow.BaseName, $device
    }

    Wait-Job $jobs | Out-Null
    $jobs | ForEach-Object { Receive-Job $_; Remove-Job $_ }
}
