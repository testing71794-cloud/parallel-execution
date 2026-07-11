#Requires -Version 5.1
function Get-FolderSizeGB([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $sum = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue
    if ($null -eq $sum -or $null -eq $sum.Sum) { return 0 }
    return [math]::Round($sum.Sum / 1GB, 2)
}

Write-Host "=== AppData\Local (top 20) ==="
$local = Join-Path $env:USERPROFILE 'AppData\Local'
Get-ChildItem -LiteralPath $local -Force -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer } | ForEach-Object {
    [PSCustomObject]@{ Name = $_.Name; 'Size (GB)' = (Get-FolderSizeGB $_.FullName); Path = $_.FullName }
} | Sort-Object 'Size (GB)' -Descending | Select-Object -First 20 | Format-Table -AutoSize

Write-Host "=== AppData\Roaming (top 12) ==="
$roaming = Join-Path $env:USERPROFILE 'AppData\Roaming'
Get-ChildItem -LiteralPath $roaming -Force -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer } | ForEach-Object {
    [PSCustomObject]@{ Name = $_.Name; 'Size (GB)' = (Get-FolderSizeGB $_.FullName) }
} | Sort-Object 'Size (GB)' -Descending | Select-Object -First 12 | Format-Table -AutoSize

Write-Host "=== Jenkins C:\Jenkins (top 10) ==="
if (Test-Path 'C:\Jenkins') {
    Get-ChildItem -LiteralPath 'C:\Jenkins' -Force -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer } | ForEach-Object {
        [PSCustomObject]@{ Name = $_.Name; 'Size (GB)' = (Get-FolderSizeGB $_.FullName) }
    } | Sort-Object 'Size (GB)' -Descending | Select-Object -First 10 | Format-Table -AutoSize
}
