# Run remaining ATP modules sequentially (same as Camera orchestrator).
$ErrorActionPreference = "Continue"
$env:JAVA_HOME = "C:\Users\HP\.jdks\jbr-17.0.8"
$env:MAESTRO_JAVA_HOME = $env:JAVA_HOME
$env:ATP_MAESTRO_STARTUP_GATE = "0"
$env:ATP_MAESTRO_WARMUP = "0"
$env:PATH = "C:\Users\HP\AppData\Local\Android\Sdk\platform-tools;" + $env:PATH
Set-Location "D:\Projects-Meastro\Kodak Smile Android-true sync"

$modules = @(
    @{ Folder = "SignUp_Login"; Suite = "atp_signup_login" },
    @{ Folder = "Onboarding"; Suite = "atp_onboarding" },
    @{ Folder = "Settings"; Suite = "atp_settings" },
    @{ Folder = "Precut"; Suite = "atp_precut" },
    @{ Folder = "Collage"; Suite = "atp_collage" }
)

$summary = @()
foreach ($m in $modules) {
    $log = "reports\run_$($m.Folder).log"
    Write-Host "`n========== $($m.Folder) ==========" -ForegroundColor Cyan
    python -m execution.atp_jenkins_orchestrator . com.kodaksmile true "C:\Tools\maestro-parallel\bin\maestro.bat" $m.Folder 2>&1 | Tee-Object -FilePath $log
    $rc = $LASTEXITCODE
    python scripts/generate_excel_report.py status "reports/$($m.Suite)_summary" $m.Suite $m.Folder
    $summary += [PSCustomObject]@{ Module = $m.Folder; ExitCode = $rc }
    if ($rc -ne 0) { Write-Host "[WARN] $($m.Folder) exit=$rc" -ForegroundColor Yellow }
}
$summary | Format-Table -AutoSize | Out-String | Write-Host
