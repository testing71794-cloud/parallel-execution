# Remove stale Maestro/Android instrumentation APK copies from user TEMP.
$ErrorActionPreference = 'SilentlyContinue'
$temp = $env:TEMP
if (-not $temp -or -not (Test-Path -LiteralPath $temp)) { exit 0 }
$files = Get-ChildItem -LiteralPath $temp -Filter 'tmp*.apk' -File -ErrorAction SilentlyContinue
if (-not $files) { exit 0 }
$sum = ($files | Measure-Object -Property Length -Sum).Sum
foreach ($f in $files) { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue }
if ($null -ne $sum -and $sum -gt 0) {
    Write-Host ("[cleanup] Removed tmp*.apk from TEMP (~{0:N1} MB)" -f ($sum / 1MB))
}
