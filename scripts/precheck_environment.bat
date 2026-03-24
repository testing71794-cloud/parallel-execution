@echo off
setlocal EnableDelayedExpansion

set "MAESTRO_OVERRIDE=%~1"
set "APP_PACKAGE=%~2"
set "EXPECTED_DEVICE=%~3"

echo =====================================
echo PRECHECK ENVIRONMENT
echo =====================================
echo User: %USERNAME%
echo Session: %SESSIONNAME%
echo Workspace: %CD%
echo.

where adb >nul 2>&1
if errorlevel 1 (
    echo ERROR: adb not found in PATH.
    exit /b 1
)

adb version
echo.

set "MAESTRO_CMD=maestro"
if not "%MAESTRO_OVERRIDE%"=="" (
    set "MAESTRO_CMD=%MAESTRO_OVERRIDE%"
) else if exist "C:\maestro\bin\maestro.exe" (
    set "MAESTRO_CMD=C:\maestro\bin\maestro.exe"
)

call "%MAESTRO_CMD%" --version
if errorlevel 1 (
    echo ERROR: Maestro command failed.
    exit /b 1
)

node --version
if errorlevel 1 exit /b 1
npm --version
if errorlevel 1 exit /b 1
python --version
if errorlevel 1 exit /b 1

echo ===== ADB DEVICES =====
adb devices
echo.

if "%EXPECTED_DEVICE%"=="" (
    set DEVICE_COUNT=0
    for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
        if "%%B"=="device" set /a DEVICE_COUNT+=1
    )
    if "!DEVICE_COUNT!"=="0" exit /b 1
) else (
    adb -s "%EXPECTED_DEVICE%" get-state >nul 2>&1
    if errorlevel 1 exit /b 1
    if not "%APP_PACKAGE%"=="" (
        adb -s "%EXPECTED_DEVICE%" shell pm list packages | findstr /i /c:"%APP_PACKAGE%" >nul
        if errorlevel 1 (
            echo WARNING: %APP_PACKAGE% not installed on %EXPECTED_DEVICE%.
        )
    )
)

if /i "%SESSIONNAME%"=="Services" (
    echo WARNING: Service session detected. UI launch can fail.
)

echo PRECHECK PASSED
exit /b 0
