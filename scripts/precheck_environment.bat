@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "MAESTRO_CMD=%~1"
set "APP_PACKAGE=%~2"
if "%APP_PACKAGE%"=="" set "APP_PACKAGE=%~1"
if "%MAESTRO_CMD%"=="%APP_PACKAGE%" set "MAESTRO_CMD="

echo =====================================
echo ENVIRONMENT PRECHECK
echo =====================================

where adb >nul 2>&1 || (echo adb not found & exit /b 1)
where python >nul 2>&1 || (echo python not found & exit /b 1)
where npm >nul 2>&1 || (echo npm not found & exit /b 1)

if not "%MAESTRO_CMD%"=="" (
    if not exist "%MAESTRO_CMD%" (
        echo Specified Maestro path not found: %MAESTRO_CMD%
        exit /b 1
    )
    echo Using Maestro: %MAESTRO_CMD%
) else (
    where maestro >nul 2>&1 || (echo maestro not found in PATH & exit /b 1)
    echo Using Maestro from PATH
)

adb start-server >nul 2>&1 || (echo adb start-server failed & exit /b 1)
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" set /a COUNT+=1
)
if not defined COUNT set COUNT=0
adb devices

echo Devices detected: %COUNT%
if %COUNT% LEQ 0 exit /b 1

echo App package: %APP_PACKAGE%
exit /b 0
