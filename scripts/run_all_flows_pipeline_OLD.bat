@echo off
setlocal EnableDelayedExpansion

echo =====================================
echo RUNNING FULL PIPELINE (FLOW BY FLOW, DEVICE BY DEVICE)
echo =====================================

set "PROJECT_DIR=%CD%"
set "NON_PRINTING_DIR=Non printing flows"
set "PRINTING_DIR=Printing Flow"
set "REPORT_DIR=%PROJECT_DIR%\reports"
set "LOG_DIR=%REPORT_DIR%\logs"

if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "MAESTRO_CMD=maestro"
if exist "C:\maestro\bin\maestro.exe" set "MAESTRO_CMD=C:\maestro\bin\maestro.exe"

echo ===== ADB DEVICES =====
adb devices

set DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        set "DEVICE_!DEVICE_COUNT!=%%A"
    )
)

if "%DEVICE_COUNT%"=="0" (
    echo ERROR: No devices connected.
    exit /b 1
)

set "OVERALL_FAILED=0"

for %%F in ("%NON_PRINTING_DIR%\*.yaml") do (
    for /L %%I in (1,1,%DEVICE_COUNT%) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        %MAESTRO_CMD% test "%%F" --device !DEVICE_ID!
        if errorlevel 1 set OVERALL_FAILED=1
    )
)

for %%F in ("%PRINTING_DIR%\*.yaml") do (
    for /L %%I in (1,1,%DEVICE_COUNT%) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        %MAESTRO_CMD% test "%%F" --device !DEVICE_ID!
        if errorlevel 1 set OVERALL_FAILED=1
    )
)

if "%OVERALL_FAILED%"=="1" (
    exit /b 1
) else (
    exit /b 0
)
