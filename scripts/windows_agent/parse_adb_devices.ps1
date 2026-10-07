# Parse "adb devices" output into one serial per line (state == device).
# ASCII-only. Writes UTF-8 no BOM for cmd consumers.
param(
    [Parameter(Mandatory = $true)][string]$InFile,
    [Parameter(Mandatory = $true)][string]$OutFile
)
$ErrorActionPreference = "SilentlyContinue"
$serials = @()
if (Test-Path -LiteralPath $InFile) {
    Get-Content -LiteralPath $InFile -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_ -match '^\s*(\S+)\s+device\s*$') {
            $serials += $Matches[1]
        }
    }
}
$utf8 = New-Object System.Text.UTF8Encoding $false
$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
[System.IO.File]::WriteAllLines($OutFile, $serials, $utf8)
Write-Output $serials.Count
