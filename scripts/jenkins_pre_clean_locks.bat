@echo off
setlocal EnableExtensions
REM Kill leftover Maestro/python holding workspace locks before deleteDir.
REM Does NOT touch Jenkins agent.jar java processes.
REM Safe with empty workspace (no repo scripts required).

echo [pre-clean] Killing leftover maestro/python (not agent.jar)...

REM Use single-quoted -Filter only — cmd.exe does not treat \" as an escape,
REM so -Filter \"Name='java.exe'\" becomes an invalid WMI query (HRESULT 0x80041017).
powershell -NoProfile -NonInteractive -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "Get-CimInstance Win32_Process -Filter 'Name=''java.exe''' |" ^
  "  Where-Object { $_.CommandLine -match 'maestro\.cli\.AppKt' } |" ^
  "  ForEach-Object { Write-Host ('[pre-clean] kill java PID=' + $_.ProcessId); taskkill /PID $_.ProcessId /T /F | Out-Null };" ^
  "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' |" ^
  "  Where-Object { $_.CommandLine -match 'jenkins_atp_stage|run_parallel' } |" ^
  "  ForEach-Object { Write-Host ('[pre-clean] kill python PID=' + $_.ProcessId); taskkill /PID $_.ProcessId /T /F | Out-Null };" ^
  "Write-Host '[pre-clean] powershell pass done'"

REM taskkill returns 128 when the image is not running — ignore that.
taskkill /IM maestro.exe /F /T >nul 2>&1
echo [pre-clean] done
exit /b 0
