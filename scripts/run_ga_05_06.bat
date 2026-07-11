@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"
call "%ROOT%\scripts\set_maestro_java.bat"

set "DEVICE=ZA222RFQ75"
set "APP=com.kodak.steptouch"
set "MAESTRO=C:\Tools\maestro-parallel\bin\maestro.bat"
set "PASS=0"
set "FAIL=0"

call :recover_drivers
echo [INFO] Fresh app state for GA_05 (recover from PM deny/settings)...
"%ADB_HOME%\adb.exe" -s %DEVICE% shell pm clear %APP%
ping 127.0.0.1 -n 3 >nul

call :run_one "GA_05 - Pinch to zoom out.yaml"
call :recover_drivers
call :run_one "GA_06 - Pinch to zoom in.yaml"

echo.
echo GA_05/06: PASS=!PASS! FAIL=!FAIL!
exit /b !FAIL!

:run_one
echo.
echo ===== %~1 =====
call "%ROOT%\scripts\run_one_flow_on_device.bat" atp_gallery "ATP TestCase Flows\gallery\%~1" %DEVICE% %APP% false "%MAESTRO%" __EMPTY__
if errorlevel 1 (
  set /a FAIL+=1
) else (
  set /a PASS+=1
)
exit /b 0

:recover_drivers
echo [INFO] Recovering ADB + Maestro driver (stop stale Appium on 4723)...
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":4723" ^| findstr "LISTENING"') do taskkill /F /PID %%P >nul 2>&1
"%ADB_HOME%\adb.exe" reconnect >nul 2>&1
ping 127.0.0.1 -n 5 >nul
exit /b 0
