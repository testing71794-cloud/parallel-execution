# Run adb with a hard timeout (Jenkins-safe).
# IMPORTANT: Never RedirectStandardOutput/Error on "adb start-server" on Windows -
# that pipe pattern deadlocks and looks like a hang/timeout.
# Prefer ADB_SERVER_PORT (default 5038) - port 5037 hangs on some CA Global agents.
# Avoid cmd.exe /c redirects when USERPROFILE has spaces (breaks quoting).
# ASCII-only strings: Unicode dashes break PowerShell parse when checkout encoding differs.
param(
    [Parameter(Mandatory = $true)][string]$AdbExe,
    [Parameter(Mandatory = $false)][string[]]$AdbArgs = @(),
    [int]$TimeoutSec = 20,
    [string]$OutFile = "",
    [switch]$EnsureServer
)

$ErrorActionPreference = "Continue"
if (-not (Test-Path -LiteralPath $AdbExe)) {
    Write-Host "ERROR: adb.exe not found: $AdbExe"
    exit 1
}

$port = $env:ADB_SERVER_PORT
if ([string]::IsNullOrWhiteSpace($port)) { $port = "5038" }
$portNum = 0
[void][int]::TryParse($port, [ref]$portNum)
if ($portNum -le 0) { $portNum = 5038; $port = "5038" }

function Test-AdbPortListening {
    param([int]$LocalPort)
    try {
        $conns = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
        if ($conns) { return $true }
    } catch {}
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect("127.0.0.1", $LocalPort, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if ($ok -and $c.Connected) {
            $c.EndConnect($iar)
            $c.Close()
            return $true
        }
        try { $c.Close() } catch {}
    } catch {}
    return $false
}

$workDir = Split-Path -Parent $AdbExe

# Ensure ADB server on ADB_SERVER_PORT without double-binding (WSAEADDRINUSE 10048).
if ($EnsureServer) {
    if (Test-AdbPortListening -LocalPort $portNum) {
        Write-Host ("[DEBUG] ADB already listening on port " + $port + " - skip nodaemon")
        exit 0
    }
    Write-Host ("[DEBUG] starting nodaemon server on port " + $port)
    Start-Process -FilePath $AdbExe -ArgumentList @("-P", $port, "nodaemon", "server") `
        -WorkingDirectory $workDir -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
    if (Test-AdbPortListening -LocalPort $portNum) {
        Write-Host ("[DEBUG] nodaemon listening on port " + $port)
        exit 0
    }
    Write-Host ("WARN: ADB port " + $port + " still not listening after nodaemon start")
    exit 0
}

if ($null -eq $AdbArgs -or $AdbArgs.Count -eq 0) {
    Write-Host "ERROR: -AdbArgs required unless -EnsureServer"
    exit 1
}

$hasPort = $false
for ($i = 0; $i -lt $AdbArgs.Count; $i++) {
    if ($AdbArgs[$i] -eq "-P" -or $AdbArgs[$i] -eq "--port") { $hasPort = $true; break }
}
if (-not $hasPort) {
    $AdbArgs = @("-P", $port) + @($AdbArgs)
    if (-not $env:ADB_SERVER_PORT) { $env:ADB_SERVER_PORT = $port }
}

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
        # start-server is a no-op if already listening - avoid needless churn across ATP modules.
        if ($isStartServer -and (Test-AdbPortListening -LocalPort $portNum)) {
            Write-Host ("[DEBUG] start-server skipped; port " + $port + " already listening")
            exit 0
        }
        $p = Start-Process -FilePath $AdbExe -ArgumentList $AdbArgs `
            -WorkingDirectory $workDir `
            -WindowStyle Hidden -PassThru
        $waitMs = [Math]::Min([Math]::Max($TimeoutSec, 1), 8) * 1000
        $finished = $p.WaitForExit($waitMs)
        if (-not $finished) {
            Write-Host ("WARN: adb " + $argText + " still running after " + ($waitMs / 1000) + "s; continuing")
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
            if ($isStartServer) {
                if (-not (Test-AdbPortListening -LocalPort $portNum)) {
                    Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 1
                    Start-Process -FilePath $AdbExe -ArgumentList @("-P", $port, "nodaemon", "server") `
                        -WorkingDirectory $workDir -WindowStyle Hidden | Out-Null
                    Start-Sleep -Seconds 2
                    Write-Host ("[DEBUG] started nodaemon server on port " + $port)
                } else {
                    Write-Host ("[DEBUG] port " + $port + " listening after start-server hang - reuse")
                }
            }
            exit 0
        }
        if ($null -eq $p.ExitCode) { exit 0 }
        exit $p.ExitCode
    }

    # devices / other: use Process + UTF8 streams.
    # Start-Process -RedirectStandardOutput writes UTF-16; cmd for /f then fails to
    # match "device" even though type/console still shows serials (Jenkins false negative).
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $AdbExe
    $psi.Arguments = ($AdbArgs | ForEach-Object {
        if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join ' '
    $psi.WorkingDirectory = $workDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    $finished = $p.WaitForExit([Math]::Max($TimeoutSec, 1) * 1000)
    if (-not $finished) {
        Write-Host ("ERROR: adb " + $argText + " timed out after " + $TimeoutSec + "s - killing hung adb")
        try { if (-not $p.HasExited) { $p.Kill() } } catch {}
        Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        # Never call Task.Result after a kill — it can block forever if pipes stay open.
        exit 2
    }
    # Drain pipes briefly; never block forever on .Result
    $outText = ""
    $errText = ""
    try { [void]$outTask.Wait(3000) } catch {}
    try { [void]$errTask.Wait(3000) } catch {}
    if ($outTask.IsCompleted) {
        try { $outText = [string]$outTask.Result } catch { $outText = "" }
    }
    if ($errTask.IsCompleted) {
        try { $errText = [string]$errTask.Result } catch { $errText = "" }
    }

    # ASCII/UTF8 no BOM so cmd for /f and batch parsers work.
    $utf8 = New-Object System.Text.UTF8Encoding $false
    if (-not $tempOut) {
        try {
            [System.IO.File]::WriteAllText($outPath, $outText, $utf8)
        } catch {
            Write-Host ("WARN: could not write OutFile: " + $_.Exception.Message)
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($outText)) {
        Write-Host $outText.TrimEnd()
    }
    if (-not [string]::IsNullOrWhiteSpace($errText)) {
        Write-Host $errText.TrimEnd()
    }
    $code = 0
    if ($null -ne $p.ExitCode) { $code = [int]$p.ExitCode }
    exit $code
} catch {
    Write-Host ("ERROR: failed to run adb: " + $_.Exception.Message)
    exit 1
}
