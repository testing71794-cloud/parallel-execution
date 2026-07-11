# Run PM_01–PM_02 permission AI flows with fresh app state per test.
param(
    [string]$Device = "ZA222RFQ75",
    [int[]]$Skip = @()
)

$ErrorActionPreference = "Continue"
$repo = Join-Path $PSScriptRoot ".."
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$maestro = "C:\Tools\maestro-parallel\bin\maestro.bat"
$permDir = Join-Path $repo "ATP TestCase Flows\permission"
$logDir = Join-Path $repo "logs\permission-suite"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:EDITING_VERIFY_SOFT = "1"
python (Join-Path $repo "scripts\ensure_editing_verify_server.py") | Out-Null

$flows = @(
    "PM_01 - All Permissions Allow with AI.yaml",
    "PM_02 - All Deny Opens Settings with AI.yaml"
)

$results = @()
foreach ($flowName in $flows) {
    if ($flowName -match 'PM_(\d+)' -and $Skip -contains [int]$Matches[1]) {
        Write-Host "SKIP $flowName" -ForegroundColor Yellow
        continue
    }
    $flow = Join-Path $permDir $flowName
    Write-Host "`n========== $flowName ==========" -ForegroundColor Cyan
    & $adb -s $Device shell pm clear com.kodak.steptouch | Out-Null
    Start-Sleep -Seconds 1
    $outFile = Join-Path $logDir (($flowName -replace '\.yaml$','') + ".log")
    & $maestro --device $Device test $flow 2>&1 | Tee-Object -FilePath $outFile
    $exit = $LASTEXITCODE
    $status = if ($exit -eq 0) { "PASS" } else { "FAIL" }
    $results += [pscustomobject]@{ Flow = $flowName; Status = $status; Exit = $exit }
    Write-Host "$status $flowName" -ForegroundColor $(if ($status -eq "PASS") { "Green" } else { "Red" })
}

Write-Host "`n========== SUMMARY =========="
$results | Format-Table -AutoSize
$fail = ($results | Where-Object Status -eq "FAIL").Count
Write-Host "Passed: $($results.Count - $fail) / $($results.Count)  Failed: $fail"
if ($fail -gt 0) { exit 1 }
