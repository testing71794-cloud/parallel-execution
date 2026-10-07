@echo off
setlocal EnableExtensions
REM Kill leftover Maestro/python/cmd holding workspace locks before deleteDir.
REM Does NOT touch Jenkins agent.jar java processes.
REM Safe with empty workspace (no repo scripts required).
REM Optional arg: workspace path (defaults to %%CD%%).

set "WS=%~1"
if "%WS%"=="" set "WS=%CD%"
set "PRE_CLEAN_WS=%WS%"
echo [pre-clean] workspace=%WS%
echo [pre-clean] Killing leftover maestro/python/cmd (not agent.jar)...

REM No -Filter \"...\"; no regex \\. — use -like / Name -eq only.
REM Do NOT kill cmd.exe merely because CommandLine contains workspace — that
REM also matches the current Jenkins durable-task wrapper and aborts the step.
powershell -NoProfile -NonInteractive -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "$ws = $env:PRE_CLEAN_WS;" ^
  "$wsOk = [bool]($ws -and $ws.Length -ge 12);" ^
  "$my = $PID;" ^
  "Get-CimInstance Win32_Process | Where-Object {" ^
  "  $_.ProcessId -ne $my -and $_.CommandLine -and" ^
  "  ($_.CommandLine -notlike '*agent.jar*') -and ($_.CommandLine -notlike '*jenkins-agent*') -and (" ^
  "    ($_.Name -eq 'java.exe' -and $_.CommandLine -like '*maestro.cli.AppKt*') -or" ^
  "    ($_.Name -eq 'java.exe' -and $wsOk -and $_.CommandLine -like ('*' + $ws + '*') -and $_.CommandLine -like '*maestro*') -or" ^
  "    ($_.Name -eq 'python.exe' -and (" ^
  "      $_.CommandLine -like '*jenkins_atp_stage*' -or $_.CommandLine -like '*run_parallel*' -or" ^
  "      $_.CommandLine -like '*atp_jenkins*' -or $_.CommandLine -like '*maestro_abort_cleanup*'" ^
  "    )) -or" ^
  "    ($_.Name -eq 'cmd.exe' -and (" ^
  "      $_.CommandLine -like '*run_one_flow_on_device.bat*' -or $_.CommandLine -like '*maestro.bat*'" ^
  "    )) -or" ^
  "    ($_.Name -eq 'maestro.exe')" ^
  "  )" ^
  "} | ForEach-Object {" ^
  "  Write-Host ('[pre-clean] taskkill name=' + $_.Name + ' pid=' + $_.ProcessId);" ^
  "  taskkill /PID $_.ProcessId /T /F | Out-Null" ^
  "};" ^
  "Write-Host '[pre-clean] powershell pass done'"

REM taskkill returns 128 when the image is not running — ignore that.
taskkill /IM maestro.exe /F /T >nul 2>&1
REM ping-sleep: timeout.exe fails under some Jenkins non-interactive redirects.
ping -n 3 127.0.0.1 >nul
echo [pre-clean] done
exit /b 0
