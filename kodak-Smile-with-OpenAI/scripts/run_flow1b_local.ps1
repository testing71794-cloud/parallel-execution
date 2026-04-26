#Requires -Version 5.1
<#
.SYNOPSIS
  Run flow1b with generated signup env (same as run_flow1b_local.bat / Jenkins).
  Prevents "undefined" in Sign Up when Maestro is run without -e.

.EXAMPLE
  .\scripts\run_flow1b_local.ps1
  .\scripts\run_flow1b_local.ps1 R58N1234ABC
#>
$bat = Join-Path $PSScriptRoot "run_flow1b_local.bat"
$device = $args[0]
if ($device) { & $bat $device } else { & $bat }
exit $LASTEXITCODE
