# Start OpenRouter verify server for GA_02 in Maestro Studio (adb fallback when PNG missing).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot
$serverScript = Join-Path $PSScriptRoot "maestro_openrouter_verify_server.py"

function Test-PortOpen([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

if (Test-PortOpen 8765) {
    Write-Host "[GA_02] Verify server already listening on http://127.0.0.1:8765"
    exit 0
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe = "py"
    $pyArgs = @("-3", $serverScript)
} else {
    $pyExe = "python"
    $pyArgs = @($serverScript)
}

Write-Host "[GA_02] Starting OpenRouter verify server (adb live capture when screenshot file missing)..."
Start-Process -FilePath $pyExe -ArgumentList $pyArgs -WorkingDirectory $RepoRoot -WindowStyle Normal | Out-Null

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if (Test-PortOpen 8765) {
        Write-Host "[GA_02] Ready. Run GA_02 in Maestro Studio now."
        exit 0
    }
}

Write-Host "[GA_02] WARN: server did not open port 8765 within 20s. Run scripts/start_maestro_verify_server.bat manually."
exit 1
