@echo off
setlocal enabledelayedexpansion

cd /d %~dp0..
echo =====================================
echo DETECTING CONNECTED DEVICES
echo =====================================

set DEVICE_COUNT=0

for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        set DEVICE!DEVICE_COUNT!=%%A
    )
)

echo Devices found: %DEVICE_COUNT%

if %DEVICE_COUNT% LEQ 0 (
    echo No devices found. Exiting...
    exit /b 1
)

echo =====================================
echo RUNNING PRINTING FLOWS
echo =====================================

call :run_flow_on_all "Printing Flow\flow1.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow2.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow3.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow4.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow5.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow6.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow7.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow8.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow9.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow10.yaml"
if errorlevel 1 exit /b 1
call :run_flow_on_all "Printing Flow\flow11.yaml"
if errorlevel 1 exit /b 1

echo All printing flows completed successfully.
exit /b 0

:run_flow_on_all
set FLOW=%~1
echo.
echo =====================================
echo Running %FLOW% on all devices
echo =====================================

if not exist reports_printing mkdir reports_printing

for /L %%I in (1,1,%DEVICE_COUNT%) do (
    start "maestro_%%I" cmd /c "maestro test -d !DEVICE%%I! "%FLOW%" --format junit > reports_printing\flow_%%~n1_device_%%I.log 2>&1"
)

:wait_loop
timeout /t 3 >nul
tasklist | findstr /i "maestro.exe" >nul
if %errorlevel%==0 goto wait_loop

echo Finished %FLOW% on all devices.
exit /b 0