#Requires -Version 5.1
# Read-only: top-level C: folder sizes + common heavy subfolders.
[CmdletBinding()]
param(
    [int] $TopN = 15
)

function Get-FolderSizeGB {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $sum = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue
        if ($null -eq $sum -or $null -eq $sum.Sum) { return 0 }
        return [math]::Round($sum.Sum / 1GB, 2)
    } catch {
        return $null
    }
}

Write-Host "=== C: drive summary ==="
$d = Get-PSDrive -Name C
$totalGb = [math]::Round(($d.Used + $d.Free) / 1GB, 2)
$usedGb = [math]::Round($d.Used / 1GB, 2)
$freeGb = [math]::Round($d.Free / 1GB, 2)
Write-Host ("Total ~ {0} GB | Used ~ {1} GB | Free ~ {2} GB" -f $totalGb, $usedGb, $freeGb)

Write-Host ""
Write-Host "=== Top-level C:\ folders ==="
$roots = Get-ChildItem -LiteralPath 'C:\' -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.PSIsContainer }
$rows = foreach ($item in $roots) {
    $gb = Get-FolderSizeGB -Path $item.FullName
    if ($null -ne $gb) {
        [PSCustomObject]@{ Folder = $item.Name; 'Size (GB)' = $gb; Path = $item.FullName }
    }
}
$rows | Sort-Object 'Size (GB)' -Descending | Select-Object -First $TopN | Format-Table -AutoSize

Write-Host "=== Notable subfolders (automation / dev caches) ==="
$notable = @(
    "$env:USERPROFILE\.maestro",
    "$env:USERPROFILE\.gradle",
    "$env:USERPROFILE\.android",
    "$env:USERPROFILE\.cursor",
    "$env:USERPROFILE\AppData\Local\Temp",
    "$env:USERPROFILE\AppData\Local\Android",
    "$env:USERPROFILE\AppData\Local\Jenkins",
    "$env:USERPROFILE\AppData\Local\pip",
    "$env:LOCALAPPDATA\npm-cache",
    "$env:USERPROFILE\AppData\Local\Packages",
    'C:\Jenkins',
    'C:\Tools'
)
$sub = foreach ($p in $notable) {
    $gb = Get-FolderSizeGB -Path $p
    if ($null -ne $gb -and $gb -gt 0) {
        [PSCustomObject]@{ Path = $p; 'Size (GB)' = $gb }
    }
}
$sub | Sort-Object 'Size (GB)' -Descending | Format-Table -AutoSize

Write-Host "=== Largest folders under $env:USERPROFILE (depth 1) ==="
$userRows = foreach ($item in (Get-ChildItem -LiteralPath $env:USERPROFILE -Force -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer })) {
    $gb = Get-FolderSizeGB -Path $item.FullName
    if ($null -ne $gb) {
        [PSCustomObject]@{ Folder = $item.Name; 'Size (GB)' = $gb }
    }
}
$userRows | Sort-Object 'Size (GB)' -Descending | Select-Object -First 12 | Format-Table -AutoSize

Write-Host "=== end ==="
