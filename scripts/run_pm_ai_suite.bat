@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"
call "%ROOT%\scripts\set_maestro_java.bat"
set "EDITING_VERIFY_SOFT=1"
python "%ROOT%\scripts\ensure_editing_verify_server.py" || exit /b 1

set "DEVICE=ZA222RFQ75"
set "APP=com.kodak.steptouch"
set "MAESTRO=C:\Tools\maestro-parallel\bin\maestro.bat"
set "PASS=0"
set "FAIL=0"

call :run_one "PM_01 - All Permissions Allow with AI.yaml"
call :run_one "PM_02 - All Deny Opens Settings with AI.yaml"

echo.
echo PM_01/02: PASS=!PASS! FAIL=!FAIL!
exit /b !FAIL!

:run_one
echo.
echo ===== %~1 =====
"%ADB_HOME%\adb.exe" -s %DEVICE% shell pm clear %APP%
call "%ROOT%\scripts\run_one_flow_on_device.bat" atp_permission "ATP TestCase Flows\permission\%~1" %DEVICE% %APP% true "%MAESTRO%" __EMPTY__
if errorlevel 1 (
  set /a FAIL+=1
) else (
  set /a PASS+=1
)
exit /b 0
