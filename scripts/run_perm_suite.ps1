# Run PERM_001–PERM_045 automated/regression cases via mapped PM Maestro flows.
# Each run: adb pm clear + launchApp clearState: true inside the flow.
param(
    [string]$Device = "ZA222RFQ75",
    [ValidateSet("Automated", "Regression", "All")]
    [string]$Mode = "Automated",
    [int[]]$Skip = @()
)

$ErrorActionPreference = "Continue"
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$maestro = "C:\Users\HP\maestro\maestro\bin\maestro.bat"
$permDir = Join-Path $PSScriptRoot "..\ATP TestCase Flows\permission"
$mappingCsv = Join-Path $permDir "atp_perm_mapping.csv"
$logDir = Join-Path $PSScriptRoot "..\logs\perm-suite"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Resolve-PmFlows {
    param([string]$MaestroFlow, [string]$PrimaryPmId)
    $flows = @()
    foreach ($part in ($MaestroFlow -split ';')) {
        $part = $part.Trim()
        if ($part -match '\.yaml$') {
            $flows += $part
            continue
        }
        if ($part -match '^PM_\d{2}$') {
            $match = Get-ChildItem -Path $permDir -Filter "$part - *.yaml" | Select-Object -First 1
            if ($match) { $flows += $match.Name }
        }
    }
    if ($flows.Count -eq 0 -and $PrimaryPmId -match '^PM_\d{2}$') {
        $match = Get-ChildItem -Path $permDir -Filter "$PrimaryPmId - *.yaml" | Select-Object -First 1
        if ($match) { $flows += $match.Name }
    }
    return $flows | Select-Object -Unique
}

$rows = Import-Csv -Path $mappingCsv
$results = @()

foreach ($row in $rows) {
    if ($Mode -eq "Automated" -and $row.Automation -ne "Automated") { continue }
    if ($Mode -eq "Regression" -and $row.Automation -ne "Regression") { continue }
    if ($Mode -eq "All" -and $row.Automation -notin @("Automated", "Regression")) { continue }

    $permId = $row.'PERM Test Case ID'
    if ($permId -match 'PERM_(\d+)' -and $Skip -contains [int]$Matches[1]) {
        Write-Host "SKIP $permId" -ForegroundColor Yellow
        continue
    }

    $pmFlows = Resolve-PmFlows -MaestroFlow $row.'Maestro Flow' -PrimaryPmId $row.'Primary PM ID'
    if ($pmFlows.Count -eq 0) {
        Write-Host "SKIP $permId (no runnable PM flow)" -ForegroundColor Yellow
        $results += [pscustomobject]@{ PERM = $permId; Flow = "(none)"; Status = "SKIP"; Exit = -1 }
        continue
    }

    foreach ($pmFile in $pmFlows) {
        $flowPath = Join-Path $permDir $pmFile
        if (-not (Test-Path $flowPath)) {
            Write-Host "MISSING $permId -> $pmFile" -ForegroundColor Red
            $results += [pscustomobject]@{ PERM = $permId; Flow = $pmFile; Status = "MISSING"; Exit = 1 }
            continue
        }

        Write-Host "`n========== $permId | $pmFile ==========" -ForegroundColor Cyan
        & $adb -s $Device shell pm clear com.kodak.steptouch | Out-Null
        Start-Sleep -Seconds 1
        $outFile = Join-Path $logDir ("${permId}_${pmFile}.log")
        & $maestro --device $Device test $flowPath 2>&1 | Tee-Object -FilePath $outFile
        $exit = $LASTEXITCODE
        $status = if ($exit -eq 0) { "PASS" } else { "FAIL" }
        $results += [pscustomobject]@{ PERM = $permId; Flow = $pmFile; Status = $status; Exit = $exit }
        Write-Host "$status $permId -> $pmFile" -ForegroundColor $(if ($status -eq "PASS") { "Green" } else { "Red" })
    }
}

Write-Host "`n========== SUMMARY =========="
$results | Format-Table -AutoSize
$fail = ($results | Where-Object Status -eq "FAIL").Count
Write-Host "Passed: $(($results | Where-Object Status -eq 'PASS').Count) / $($results.Count)  Failed: $fail"
if ($fail -gt 0) { exit 1 }
