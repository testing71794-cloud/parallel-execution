@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "DEV=%~1"
if "%DEV%"=="" ( echo USAGE: run_atp_on_device.bat ^<device_serial^> & exit /b 1 )
cd /d "%~dp0..\.."
set "REPO=%CD%"
set "A=%REPO%\automation_with_testcases"
if not exist "%A%\config.yaml" ( echo ERROR: no config.yaml & exit /b 1 )
if not exist "%REPO%\scripts\set_maestro_java.bat" ( echo ERROR: set_maestro_java & exit /b 1 )

if "%MAESTRO_CMD%"=="" ( set "MJC=maestro" ) else ( set "MJC=%MAESTRO_CMD%" )
call "%REPO%\scripts\set_maestro_java.bat" "%MJC%"
if errorlevel 1 ( echo ERROR: set_maestro_java & exit /b 1 )
if exist "%MAESTRO_HOME%\maestro.bat" ( set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.bat" ) else if exist "%MAESTRO_HOME%\maestro.cmd" ( set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.cmd" ) else ( set "MAESTRO_BIN=%MJC%" )
where python >nul 2>&1 || ( echo python not on PATH & exit /b 1 )
where adb >nul 2>&1 || ( echo adb not on PATH & exit /b 1 )

for /f "delims=" %%S in ('python "%REPO%\scripts\print_path_segment.py" "%DEV%" 2^>nul') do set "DEV_SEG=%%S"
if "!DEV_SEG!"=="" set "DEV_SEG=unk"
set "LDIR=%A%\logs\!DEV_SEG!"
set "RDIR=%A%\results\!DEV_SEG!"
set "SDIR=%A%\screenshots\!DEV_SEG!"
for %%D in (logs results screenshots) do if not exist "%A%\%%D" mkdir "%A%\%%D"
if not exist "%LDIR%" mkdir "%LDIR%" & if not exist "%RDIR%" mkdir "%RDIR%" & if not exist "%SDIR%" mkdir "%SDIR%"
if not exist "%REPO%\status" mkdir "%REPO%\status"

set "MLOG=%LDIR%\last_maestro.log"
set "JUNIT=%RDIR%\junit.xml"
set "FLOW=signup_atp_smoke"
set "SAFE_DEV=%DEV: =_%"
set "ATUS=%REPO%\status\atp__%FLOW%__!SAFE_DEV!.txt"
set "FHY=%A%\flows\signup\signup_atp_smoke.yaml"
set "KODAK_DEVICE_ID=%DEV%" & set "ANDROID_SERIAL=%DEV%"

set "EC=0" & set "ST=FAIL" & set "EERR=ok"
for /f "delims=" %%N in ('python "%REPO%\scripts\resolve_device_name.py" "%DEV%" 2^>nul') do set "DN=%%N"
if not defined DN set "DN=%DEV%"

(
  echo === ATP device worker ===
  echo %date% %time%  dev="%DEV%"  seg=!DEV_SEG!
  echo REPO: %REPO%
  echo CWD: %CD%
  echo CONFIG_MAESTRO_CMD: %MJC%
  echo FLOW_YAML: !FHY!
  echo MAESTRO: !MAESTRO_BIN!  JAVA: %JAVA_HOME%  ADB: %ANDROID_HOME%
) > "%MLOG%"

where java >> "%MLOG%" 2>&1
java -version >> "%MLOG%" 2>&1
echo.>> "%MLOG%"

adb -s "%DEV%" get-state >> "%MLOG%" 2>&1
if errorlevel 1 (
  set "EC=2" & set "EERR=adb get-state failed" & set "ST=FAIL"
  python "%A%\scripts\write_atp_status_json.py" "%RDIR%" "%DEV%" "%DN%" "!DEV_SEG!" "%FLOW%" "2" "%MLOG%" "%JUNIT%" 2>>"%MLOG%"
  goto :write_out
)

echo --- maestro --- >> "%MLOG%"
call "!MAESTRO_BIN!" --device "%DEV%" test "%FHY%" --config "%A%\config.yaml" --format junit --output "%JUNIT%" >> "%MLOG%" 2>&1
set "EC=%ERRORLEVEL%"
if "%EC%"=="0" ( set "ST=PASS" & set "EERR=OK" ) else ( set "ST=FAIL" & set "EERR=Maestro exit %EC%")

python "%A%\scripts\write_atp_status_json.py" "%RDIR%" "%DEV%" "%DN%" "!DEV_SEG!" "%FLOW%" "%EC%" "%MLOG%" "%JUNIT%" >> "%MLOG%" 2>&1

:write_out
> "%ATUS%" (
  echo suite=atp
  echo flow=%FLOW%
  echo device=%DEV%
  echo device_id=%DEV%
  echo device_name=%DN%
  echo status=%ST%
  echo final_status=%ST%
  echo exit_code=%EC%
  echo reason=ATP
  echo log_path=%MLOG%
  echo first_log_path=%MLOG%
  echo retry_count=0
  echo first_error=%EERR%
  echo final_error=%EERR%
  echo error_message=%EERR%
  echo timestamp=%date% %time%
  echo dev_segment=%DEV_SEG%
  echo screenshot_path=%SDIR%
)
exit /b %EC%
