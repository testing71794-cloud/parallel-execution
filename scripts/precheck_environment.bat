@echo off
setlocal EnableDelayedExpansion

set "MAESTRO_OVERRIDE=%~1"
set "APP_PACKAGE=%~2"

set "MAESTRO_CMD=maestro"
if not "%MAESTRO_OVERRIDE%"=="" (
    set "MAESTRO_CMD=%MAESTRO_OVERRIDE%"
) else if exist "C:\maestro\bin\maestro.exe" (
    set "MAESTRO_CMD=C:\maestro\bin\maestro.exe"
)

echo =====================================
echo PRECHECK ENVIRONMENT
echo =====================================
echo User: %USERNAME%
echo Session: %SESSIONNAME%
echo Workspace: %CD%
echo Maestro command: %MAESTRO_CMD%
echo.

where adb >nul 2>&1
if errorlevel 1 (
    echo ERROR: adb not found in PATH.
    exit /b 1
)
adb version
echo.

call "%MAESTRO_CMD%" --version
if errorlevel 1 (
    echo ERROR: Maestro command failed.
    exit /b 1
)
echo.

node --version
if errorlevel 1 (
    echo ERROR: Node.js not available.
    exit /b 1
)

npm --version
if errorlevel 1 (
    echo ERROR: npm not available.
    exit /b 1
)

python --version
if errorlevel 1 (
    echo ERROR: Python not available.
    exit /b 1
)
echo.

echo ===== ADB DEVICES =====
adb devices
echo.

set /a DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" set /a DEVICE_COUNT+=1
)
if !DEVICE_COUNT! EQU 0 (
    echo ERROR: No Android devices connected.
    exit /b 1
)

if not "%APP_PACKAGE%"=="" (
    for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
        if /I "%%B"=="device" (
            adb -s "%%A" shell pm list packages | findstr /i /c:"%APP_PACKAGE%" >nul
            if errorlevel 1 (
                echo WARNING: %APP_PACKAGE% not installed on %%A.
            )
        )
    )
)

if /I "%SESSIONNAME%"=="Services" (
    echo WARNING: Service session detected. UI launch can fail in a Windows service session.
)

echo PRECHECK PASSED
exit /b 0
