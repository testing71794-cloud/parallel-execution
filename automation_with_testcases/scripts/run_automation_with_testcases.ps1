param([string]$RepoRoot = "")
$ErrorActionPreference = "Continue"
if ($RepoRoot -eq "") { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$logDir = Join-Path $RepoRoot "automation_with_testcases\logs"
$orchestratorLog = Join-Path $logDir "atp_orchestrator.log"
$null = New-Item -ItemType Directory -Force -Path $logDir -ErrorAction SilentlyContinue
function Log([string]$m) {
  $t = (Get-Date -Format "o")
  $line = "[$t] $m"
  try { Add-Content -LiteralPath $orchestratorLog -Encoding UTF8 -Value $line } catch { }
  Write-Host $line
}
Log "ATP orchestrator start. Repo: $RepoRoot"
$devices = @()
$dd = Join-Path $RepoRoot "detected_devices.txt"
if (Test-Path -LiteralPath $dd) {
  Get-Content -LiteralPath $dd -ErrorAction SilentlyContinue | ForEach-Object { $t = $_.Trim(); if ($t -match "^\S+$" -and $t -ne "List") { $devices += $t } }
}
$devices = $devices | Select-Object -Unique
if ($devices.Count -eq 0) {
  $adbOut = & adb devices 2>&1
  foreach ($line in $adbOut) { if ($line -match "^(?<id>\S+)\s+device$") { $devices += $matches['id'] } }
  $devices = $devices | Select-Object -Unique
}
$merge = Join-Path $RepoRoot "automation_with_testcases\scripts\merge_atp_device_results.py"
function Run-Merge {
  if (-not (Test-Path -LiteralPath $merge)) { return }
  & python $merge
}
if ($devices.Count -eq 0) {
  Log "No devices — writing fallback report."
  Run-Merge
  exit 1
}
Log "Devices: $($devices -join ', ')"
$bat = Join-Path $RepoRoot "automation_with_testcases\scripts\run_atp_on_device.bat"
$procs = @()
foreach ($d in $devices) {
  Log "Start worker: $d"
  $p = Start-Process -FilePath $bat -ArgumentList $d -WorkingDirectory $RepoRoot -PassThru -NoNewWindow -WindowStyle Minimized
  $procs += [pscustomobject]@{ P = $p; D = $d }
}
$bad = $false
foreach ($o in $procs) {
  if ($null -eq $o.P) { $bad = $true; continue }
  $o.P.WaitForExit()
  $x = $o.P.ExitCode
  Log "Device $($o.D) exit $x"
  if ($x -ne 0) { $bad = $true }
}
Run-Merge
if ($bad) { exit 1 } else { exit 0 }
