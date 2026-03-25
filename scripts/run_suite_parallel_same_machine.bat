@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_DIR=%~2"
set "MAESTRO_OVERRIDE=%~3"
set "APP_PACKAGE=%~4"
set "RETRY_FAILED=%~5"

set "PROJECT_DIR=%CD%"
set "COLLECT_DIR=%PROJECT_DIR%\collected-artifacts"
set "PIPELINE_FAIL_FLAG=%PROJECT_DIR%\pipeline_failed.flag"
set "RUNNER_DIR=%PROJECT_DIR%\temp-runners"
set "PS_SCRIPT=%RUNNER_DIR%\run_parallel_jobs.ps1"

if not exist "%COLLECT_DIR%" mkdir "%COLLECT_DIR%"
if not exist "%RUNNER_DIR%" mkdir "%RUNNER_DIR%"
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"
if not exist "%PROJECT_DIR%\status" mkdir "%PROJECT_DIR%\status"

del /q "%PROJECT_DIR%\*.failed" >nul 2>&1
del /q "%RUNNER_DIR%\*" >nul 2>&1

set /a DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
  if /I "%%B"=="device" (
    set /a DEVICE_COUNT+=1
    set "DEVICE_!DEVICE_COUNT!=%%A"
  )
)

if !DEVICE_COUNT! EQU 0 (
  echo ERROR: No Android devices connected.
  > "%PIPELINE_FAIL_FLAG%" echo 1
  exit /b 1
)

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo Suite: %SUITE_NAME%
echo Flow dir: %FLOW_DIR%
echo Devices found: !DEVICE_COUNT!
echo Retry failed once: %RETRY_FAILED%
echo.

for %%F in ("%FLOW_DIR%\*.yaml") do (
  set "FLOW_PATH=%%~fF"
  set "FLOW_NAME=%%~nF"

  echo =====================================
  echo Running !FLOW_NAME! on all devices in parallel
  echo =====================================

  > "%PS_SCRIPT%" echo $ErrorActionPreference = Continue
  >> "%PS_SCRIPT%" echo $jobs = @()

  for /L %%I in (1,1,!DEVICE_COUNT!) do (
    call set "DEVICE_ID=%%DEVICE_%%I%%"
    set "SAFE_DEVICE_ID=!DEVICE_ID::=_%!"
    set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:/=_%!"
    set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:\=_%!"
    set "FAIL_FLAG=%PROJECT_DIR%\%SUITE_NAME%__!FLOW_NAME!__!SAFE_DEVICE_ID!.failed"

    del /q "!FAIL_FLAG!" >nul 2>&1

    >> "%PS_SCRIPT%" echo $jobs += Start-Job -ScriptBlock {
    >> "%PS_SCRIPT%" echo ^& cmd.exe /d /c "cd /d ""%PROJECT_DIR%"" ^&^& call scripts\run_one_flow_on_device.bat ""%SUITE_NAME%"" ""!FLOW_NAME!"" ""!FLOW_PATH!"" ""!DEVICE_ID!"" ""%MAESTRO_OVERRIDE%"" ""%APP_PACKAGE%"" ""%RETRY_FAILED%"""
    >> "%PS_SCRIPT%" echo if ^($LASTEXITCODE -ne 0^) { Set-Content -Path "!FAIL_FLAG!" -Value "1" }
    >> "%PS_SCRIPT%" echo }
  )

  >> "%PS_SCRIPT%" echo Wait-Job -Job $jobs ^| Out-Null
  >> "%PS_SCRIPT%" echo Receive-Job -Job $jobs -Keep ^| Out-Host
  >> "%PS_SCRIPT%" echo Remove-Job -Job $jobs -Force ^| Out-Null

  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
  if errorlevel 1 (
    > "%PIPELINE_FAIL_FLAG%" echo 1
  )

  for /L %%I in (1,1,!DEVICE_COUNT!) do (
    call set "DEVICE_ID=%%DEVICE_%%I%%"
    set "SAFE_DEVICE_ID=!DEVICE_ID::=_%!"
    set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:/=_%!"
    set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:\=_%!"
    if exist "%PROJECT_DIR%\%SUITE_NAME%__!FLOW_NAME!__!SAFE_DEVICE_ID!.failed" (
      > "%PIPELINE_FAIL_FLAG%" echo 1
    )
  )
)

if exist reports xcopy /E /I /Y reports "%COLLECT_DIR%\reports" >nul
if exist .maestro\screenshots xcopy /E /I /Y .maestro\screenshots "%COLLECT_DIR%\.maestro\screenshots" >nul
if exist status xcopy /E /I /Y status "%COLLECT_DIR%\status" >nul
if exist logs xcopy /E /I /Y logs "%COLLECT_DIR%\logs" >nul

if exist "%PIPELINE_FAIL_FLAG%" exit /b 1
exit /b 0