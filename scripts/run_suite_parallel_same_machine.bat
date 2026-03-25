@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_DIR=%~2"

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo Suite: %SUITE_NAME%
echo Flow dir: %FLOW_DIR%
echo.

:: Detect devices
set /a DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        set "DEVICE_!DEVICE_COUNT!=%%A"
    )
)

if %DEVICE_COUNT%==0 (
    echo No devices found
    exit /b 1
)

echo Devices found: %DEVICE_COUNT%

:: Loop flows
for %%F in ("%FLOW_DIR%\*.yaml") do (
    set "FLOW_PATH=%%~fF"
    set "FLOW_NAME=%%~nF"

    echo =====================================
    echo Running !FLOW_NAME! on all devices
    echo =====================================

    :: RUN PARALLEL (FIXED - NO cmd /c)
    for /L %%I in (1,1,%DEVICE_COUNT%) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        start "" /b scripts\run_one_flow_on_device.bat %SUITE_NAME% !FLOW_NAME! "!FLOW_PATH!" !DEVICE_ID!
    )

    :: Wait for all processes to finish
    timeout /t 15 >nul
)

exit /b 0