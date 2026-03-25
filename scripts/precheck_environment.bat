@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "APP_PACKAGE=%~1"

echo =====================================
echo ENVIRONMENT PRECHECK
echo =====================================
where adb >nul 2>&1 || (echo adb not found & exit /b 1)
where python >nul 2>&1 || (echo python not found & exit /b 1)
where npm >nul 2>&1 || (echo npm not found & exit /b 1)
where maestro >nul 2>&1 || (echo maestro not found & exit /b 1)

adb start-server >nul 2>&1
adb devices

set /a COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" set /a COUNT+=1
)

echo Devices detected: !COUNT!
if !COUNT! LEQ 0 exit /b 1

echo App package: %APP_PACKAGE%
exit /b 0
