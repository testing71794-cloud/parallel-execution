@echo off
setlocal EnableExtensions
REM Kill leftover Maestro automation after Jenkins Stop / stage end.
REM Safe standalone: works even if workspace checkout is incomplete.
set "REPO=%~1"
if "%REPO%"=="" set "REPO=%CD%"
cd /d "%REPO%" 2>nul

echo [abort-cleanup] workspace=%CD%
echo [abort-cleanup] Killing maestro.cli.AppKt java processes and wrappers...

REM Prefer Python module when present (owned-pid aware + adb forward cleanup).
if exist "execution\maestro_abort_cleanup.py" (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -m execution.maestro_abort_cleanup jenkins_post "%CD%"
    goto :after_python
  )
)

REM Fallback: PowerShell-only host kill (no repo imports).
powershell -NoProfile -NonInteractive -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" |" ^
  "  Where-Object { $_.CommandLine -match 'maestro\.cli\.AppKt' } |" ^
  "  ForEach-Object { Write-Host ('[abort-cleanup] taskkill java pid=' + $_.ProcessId); taskkill /PID $_.ProcessId /T /F | Out-Null };" ^
  "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" |" ^
  "  Where-Object { $_.CommandLine -match 'run_one_flow_on_device\.bat|maestro\.bat' } |" ^
  "  ForEach-Object { Write-Host ('[abort-cleanup] taskkill cmd pid=' + $_.ProcessId); taskkill /PID $_.ProcessId /T /F | Out-Null };" ^
  "Write-Host '[abort-cleanup] powershell pass done'"

:after_python
taskkill /IM maestro.exe /F /T >nul 2>&1
echo [abort-cleanup] done
exit /b 0
