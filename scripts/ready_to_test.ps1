# Verify the repo is ready: Python deps, npm deps, unit tests, optional one-flow Maestro smoke on first USB device.
# Usage (from repo root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ready_to_test.ps1
#   powershell -File scripts\ready_to_test.ps1 -WithDeviceSmoke
#   powershell -File scripts\ready_to_test.ps1 -WithDeviceSmoke -AppPackage com.kodaksmile

param(
    [switch] $WithDeviceSmoke,
    [string] $AppPackage = "com.kodaksmile",
    [string] $MaestroCmd = "maestro.bat",
    [string] $SmokeFlow = "Non printing flows\flow1.yaml"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot
$env:WORKSPACE = $RepoRoot

function Write-Step { param([string] $Message) Write-Host "" ; Write-Host "==> $Message" -ForegroundColor Cyan }

Write-Step "Repository root: $RepoRoot"

Write-Step "Python: install dependencies"
python -m pip install -q -r (Join-Path $RepoRoot "scripts\requirements-python.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Step "Node: install dependencies (root package.json)"
if (Test-Path (Join-Path $RepoRoot "package-lock.json")) {
    Push-Location $RepoRoot
    npm ci
    Pop-Location
} else {
    Push-Location $RepoRoot
    npm install
    Pop-Location
}
if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

Write-Step "Python: unit tests (intelligent_platform)"
python -m pytest (Join-Path $RepoRoot "intelligent_platform\tests") -q --tb=short
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

if (-not $WithDeviceSmoke) {
    Write-Host ""
    Write-Host "OK: deps + unit tests passed." -ForegroundColor Green
    Write-Host "Next: connect an Android device (USB, authorized), set ANDROID_HOME if needed, then:" -ForegroundColor Yellow
    Write-Host "  powershell -File scripts\ready_to_test.ps1 -WithDeviceSmoke" -ForegroundColor Yellow
    exit 0
}

Write-Step "ADB: first connected device"
$null = & adb start-server 2>&1
$lines = & adb devices 2>&1
$serial = $null
foreach ($line in $lines) {
    if ($line -match "^\s*([^\s]+)\s+device\s*$") {
        $serial = $Matches[1]
        break
    }
}
if (-not $serial) {
    Write-Warning "No device in 'adb devices' (authorized). Skipping Maestro smoke. USB debugging + RSA trust required."
    exit 0
}

$flowPath = Join-Path $RepoRoot $SmokeFlow
if (-not (Test-Path $flowPath)) {
    throw "Smoke flow not found: $flowPath"
}

Write-Step "Maestro: single-flow smoke on device $serial  ($SmokeFlow)"
$bat = Join-Path $RepoRoot "scripts\run_one_flow_on_device.bat"
& cmd /c "call `"$bat`" nonprinting `"$SmokeFlow`" `"$serial`" `"$AppPackage`" true `"$MaestroCmd`""
$code = $LASTEXITCODE
Write-Host ""
if ($code -eq 0) {
    Write-Host "OK: device smoke completed (exit 0)." -ForegroundColor Green
} else {
    Write-Warning "Device smoke ended with exit code $code. Check reports\nonprinting\logs and status\ for details."
    exit $code
}
