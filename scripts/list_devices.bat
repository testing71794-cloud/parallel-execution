@echo off
setlocal EnableExtensions EnableDelayedExpansion

call "%~dp0set_maestro_java.bat" || exit /b 1

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "OUT_FILE=%REPO_ROOT%\detected_devices.txt"

echo =========================
echo Connected Android devices
echo =========================

del /q "%OUT_FILE%" 2>nul
adb start-server >nul 2>&1 || (
    echo ERROR: unable to start adb
    exit /b 1
)

adb devices

(
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" echo %%A
)
) > "%OUT_FILE%"

set /a COUNT=0
for /f %%A in (%OUT_FILE%) do set /a COUNT+=1

echo.
echo Devices detected: !COUNT!
echo Device list saved to: "%OUT_FILE%"

if !COUNT! LEQ 0 exit /b 1
exit /b 0
