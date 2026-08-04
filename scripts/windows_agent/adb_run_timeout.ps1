# Run adb with a hard timeout (Jenkins-safe).
# IMPORTANT: Never RedirectStandardOutput/Error on "adb start-server" on Windows —
# that pipe pattern deadlocks and looks like a hang/timeout.
# Prefer ADB_SERVER_PORT (default 5038) — port 5037 hangs on some CA Global agents.
# Avoid cmd.exe /c redirects when USERPROFILE has spaces (breaks quoting).
param(
    [Parameter(Mandatory = $true)][string]$AdbExe,
    [Parameter(Mandatory = $true)][string[]]$AdbArgs,
    [int]$TimeoutSec = 20,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Continue"
if (-not (Test-Path -LiteralPath $AdbExe)) {
    Write-Host "ERROR: adb.exe not found: $AdbExe"
    exit 1
}

$port = $env:ADB_SERVER_PORT
if ([string]::IsNullOrWhiteSpace($port)) { $port = "5038" }
$hasPort = $false
for ($i = 0; $i -lt $AdbArgs.Count; $i++) {
    if ($AdbArgs[$i] -eq "-P" -or $AdbArgs[$i] -eq "--port") { $hasPort = $true; break }
}
if (-not $hasPort) {
    $AdbArgs = @("-P", $port) + @($AdbArgs)
    if (-not $env:ADB_SERVER_PORT) { $env:ADB_SERVER_PORT = $port }
}

$workDir = Split-Path -Parent $AdbExe
$argText = ($AdbArgs -join " ")
$cmdName = ""
for ($i = 0; $i -lt $AdbArgs.Count; $i++) {
    if ($AdbArgs[$i] -eq "-P" -or $AdbArgs[$i] -eq "--port") { $i++; continue }
    $cmdName = [string]$AdbArgs[$i]
    break
}
$isStartServer = ($cmdName -eq "start-server")
$isKillServer = ($cmdName -eq "kill-server")

$outPath = $OutFile
$tempOut = $false
if ([string]::IsNullOrWhiteSpace($outPath)) {
    $outPath = Join-Path $env:TEMP ("adb_out_" + [guid]::NewGuid().ToString("N") + ".txt")
    $tempOut = $true
}
$errPath = Join-Path $env:TEMP ("adb_err_" + [guid]::NewGuid().ToString("N") + ".txt")

try {
    if ($isStartServer -or $isKillServer) {
        $p = Start-Process -FilePath $AdbExe -ArgumentList $AdbArgs `
            -WorkingDirectory $workDir `
            -WindowStyle Hidden -PassThru
        $waitMs = [Math]::Min([Math]::Max($TimeoutSec, 1), 8) * 1000
        $finished = $p.WaitForExit($waitMs)
        if (-not $finished) {
            Write-Host ("WARN: adb " + $argText + " still running after " + ($waitMs / 1000) + "s; continuing")
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
            if ($isStartServer) {
                Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
                Start-Process -FilePath $AdbExe -ArgumentList @("-P", $port, "nodaemon", "server") `
                    -WorkingDirectory $workDir -WindowStyle Hidden
                Start-Sleep -Seconds 2
                Write-Host ("[DEBUG] started nodaemon server on port " + $port)
            }
            exit 0
        }
        if ($null -eq $p.ExitCode) { exit 0 }
        exit $p.ExitCode
    }

    # devices / other: redirect via Start-Process (safe with spaces in paths)
    Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $errPath -Force -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $AdbExe -ArgumentList $AdbArgs `
        -WorkingDirectory $workDir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outPath `
        -RedirectStandardError $errPath
    $finished = $p.WaitForExit($TimeoutSec * 1000)
    if (-not $finished) {
        Write-Host ("ERROR: adb " + $argText + " timed out after " + $TimeoutSec + "s - killing hung adb")
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $outPath) { Get-Content -LiteralPath $outPath -ErrorAction SilentlyContinue | Write-Host }
        if (Test-Path -LiteralPath $errPath) { Get-Content -LiteralPath $errPath -ErrorAction SilentlyContinue | Write-Host }
        exit 2
    }
    if (Test-Path -LiteralPath $outPath) {
        Get-Content -LiteralPath $outPath -ErrorAction SilentlyContinue | Write-Host
    }
    if (Test-Path -LiteralPath $errPath) {
        $errText = Get-Content -LiteralPath $errPath -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($errText)) { Write-Host $errText.TrimEnd() }
    }
    $code = 0
    if ($null -ne $p.ExitCode) { $code = [int]$p.ExitCode }
    if ($tempOut -and (Test-Path -LiteralPath $outPath)) {
        Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $errPath -Force -ErrorAction SilentlyContinue
    exit $code
} catch {
    Write-Host ("ERROR: failed to run adb: " + $_.Exception.Message)
    exit 1
}
