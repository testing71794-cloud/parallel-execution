# Local smoke test: syntax + quoted paths + Process.ExitCode (no adb/Maestro).
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_test_parallel_runner.ps1
$ErrorActionPreference = "Stop"

$main = Join-Path $PSScriptRoot "run_suite_parallel_same_machine.ps1"
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($main, [ref]$null, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) {
    Write-Host "PARSE FAILED:"
    $parseErrors | ForEach-Object { Write-Host $_ }
    exit 1
}
Write-Host "[OK] Syntax: $main"

# Same rules as Escape-CmdArg / Build-RunnerCmdLine in the main script
function Escape-CmdArg([string]$s) {
    if ($null -eq $s) { return '""' }
    return '"' + ($s.Replace('"', '""')) + '"'
}

$repo = "C:\fake\repo"
$bat = Join-Path $repo "scripts\run_one_flow_on_device.bat"
$flow = Join-Path $repo "Non printing flows\flow1.yaml"
$parts = @(
    "/c", "call",
    (Escape-CmdArg $bat),
    (Escape-CmdArg "nonprinting"),
    (Escape-CmdArg $flow),
    (Escape-CmdArg "flow1"),
    (Escape-CmdArg "SERIAL1"),
    (Escape-CmdArg "com.kodaksmile"),
    (Escape-CmdArg "true"),
    (Escape-CmdArg "__EMPTY__"),
    (Escape-CmdArg "__EMPTY__")
)
$line = $parts -join " "
if ($line -notmatch 'Non printing flows') { throw "Cmd line dropped path segment: $line" }
if ($line -notmatch '"[^"]*Non printing flows\\flow1\.yaml"') { throw "Flow path not one quoted token: $line" }
Write-Host "[OK] Quoted path with spaces preserved in cmd line"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c exit 42"
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$p = New-Object System.Diagnostics.Process
$p.StartInfo = $psi
[void]$p.Start()
$p.WaitForExit()
if ($p.ExitCode -ne 42) { throw "Process.ExitCode expected 42, got $($p.ExitCode)" }
Write-Host "[OK] System.Diagnostics.Process ExitCode (42)"

Write-Host ""
Write-Host "ALL SMOKE TESTS PASSED."
exit 0
