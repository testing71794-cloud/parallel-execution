@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================================
rem Local / IDE: run flow1b with generated EMAIL, FULL_NAME, PASSWORD
rem (same pipeline as run_one_flow_on_device for flow1b — avoids "undefined" inputs)
rem
rem   scripts\run_flow1b_local.bat
rem   scripts\run_flow1b_local.bat R58N1234ABC
rem
rem If you omit the serial, the first "device" line from adb is used. With
rem several devices, pass the serial you want.
rem
rem flow1b: FULL_NAME=Nitesh, PASSWORD=252546Nm#, EMAIL=kodak_<ts>_<random>@test.com
rem (same as run_one_flow_on_device for flow1b; unique per run/device for parallel)
rem ============================================================================

set "MAESTRO_CMD=maestro"
if not "%MAESTRO_CMD_ARG%"=="" set "MAESTRO_CMD=%MAESTRO_CMD_ARG%"

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

call "%REPO_ROOT%\scripts\set_maestro_java.bat" "%MAESTRO_CMD%"
if errorlevel 1 (
  echo [run_flow1b_local] set_maestro_java failed.
  exit /b 1
)

if exist "%MAESTRO_HOME%\maestro.bat" (
  set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.bat"
) else if exist "%MAESTRO_HOME%\maestro.cmd" (
  set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.cmd"
) else (
  set "MAESTRO_BIN=maestro"
)

set "DEVICE_ID=%~1"
if not defined DEVICE_ID set "DEVICE_ID="

if not defined DEVICE_ID (
  for /f "skip=1 tokens=1,2" %%A in ('adb devices 2^>nul') do (
    if /I "%%B"=="device" if not defined DEVICE_ID set "DEVICE_ID=%%A"
  )
)

if not defined DEVICE_ID (
  echo ERROR: No ADB device found. Connect a device, authorize USB debugging, or run:
  echo   %~nx0 ^<device_serial^>
  exit /b 1
)

echo [run_flow1b_local] Device: !DEVICE_ID!
if defined ADB_HOME if exist "%ADB_HOME%\adb.exe" (
  set "PATH=%ADB_HOME%;%PATH%"
) else (
  where adb >nul 2>&1
)

set "FLOW1B=%REPO_ROOT%\Non printing flows\flow1b.yaml"
if not exist "!FLOW1B!" (
  echo ERROR: Flow not found: !FLOW1B!
  exit /b 1
)

where python >nul 2>&1 || ( echo ERROR: python not on PATH. & exit /b 1 )

call "%REPO_ROOT%\scripts\flow1b_set_signup_env.bat"
if errorlevel 1 (
  echo ERROR: flow1b_set_signup_env failed
  exit /b 1
)

if not defined EMAIL ( echo ERROR: SIGNUP env not set. & exit /b 1 )
if not defined FULL_NAME ( echo ERROR: FULL_NAME not set. & exit /b 1 )
if not defined PASSWORD ( echo ERROR: PASSWORD not set. & exit /b 1 )

echo [run_flow1b_local] EMAIL=!EMAIL!
echo.
echo [run_flow1b_local] Starting Maestro... (PASSWORD is not printed below^)
set "MAESTRO_ARGS=test -e FULL_NAME=!FULL_NAME! -e EMAIL=!EMAIL! -e PASSWORD=!PASSWORD! "!FLOW1B!" --device "!DEVICE_ID!"
echo [run_flow1b_local] !MAESTRO_BIN! test -e FULL_NAME=!FULL_NAME! -e EMAIL=!EMAIL! -e PASSWORD=omitted "!FLOW1B!" --device "!DEVICE_ID!"
echo.
call "%MAESTRO_BIN%" !MAESTRO_ARGS!
set "MEXIT=!ERRORLEVEL!"

if not "!MEXIT!"=="0" (
  echo.
  echo [run_flow1b_local] Maestro exit code: !MEXIT!
) else (
  echo.
  echo [run_flow1b_local] OK
)
exit /b !MEXIT!
