@echo off
setlocal EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_DIR=%~2"
set "MAESTRO_OVERRIDE=%~3"
set "APP_PACKAGE=%~4"
set "RETRY_FAILED=%~5"

set "PROJECT_DIR=%CD%"
set "COLLECT_DIR=%PROJECT_DIR%\collected-artifacts"
set "PIPELINE_FAIL_FLAG=%PROJECT_DIR%\pipeline_failed.flag"

if not exist "%COLLECT_DIR%" mkdir "%COLLECT_DIR%"

echo =====================================
echo RUN SUITE SAME MACHINE
echo =====================================
echo Suite: %SUITE_NAME%
echo Flow dir: %FLOW_DIR%
echo Retry failed once: %RETRY_FAILED%
echo.

echo ===== ADB DEVICES =====
adb devices
echo.

set DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        set "DEVICE_!DEVICE_COUNT!=%%A"
    )
)

if "%DEVICE_COUNT%"=="0" (
    echo ERROR: No Android devices connected.
    echo 1> "%PIPELINE_FAIL_FLAG%"
    exit /b 1
)

for %%F in ("%FLOW_DIR%\*.yaml") do (
    set "FLOW_PATH=%%F"
    set "FLOW_NAME=%%~nF"

    echo =====================================
    echo Running !FLOW_NAME! on all devices sequentially
    echo =====================================

    for /L %%I in (1,1,%DEVICE_COUNT%) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        call scripts\run_one_flow_on_device.bat "%SUITE_NAME%" "!FLOW_NAME!" "!FLOW_PATH!" "!DEVICE_ID!" "%MAESTRO_OVERRIDE%" "%APP_PACKAGE%" "%RETRY_FAILED%"
        if errorlevel 1 (
            echo 1> "%PIPELINE_FAIL_FLAG%"
        )
    )
)

if exist reports xcopy /E /I /Y reports "%COLLECT_DIR%\reports" >nul
if exist .maestro\screenshots xcopy /E /I /Y .maestro\screenshots "%COLLECT_DIR%\.maestro\screenshots" >nul
if exist status xcopy /E /I /Y status "%COLLECT_DIR%\status" >nul

if exist "%PIPELINE_FAIL_FLAG%" (
    exit /b 1
)

exit /b 0
