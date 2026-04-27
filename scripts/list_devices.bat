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

where adb 2>nul
if errorlevel 1 (
    echo ERROR: adb not on PATH. Set ANDROID_HOME / SDK in Jenkins; ensure set_maestro_java runs first.
    exit /b 1
)

echo Starting ADB server once...
adb start-server >nul 2>&1 || (
    echo ERROR: failed to start adb server. Check USB/debug permissions and Android SDK path.
    exit /b 1
)

echo Listing devices ^(only serials in state "device" are written to detected_devices.txt^)...
adb devices || (
    echo ERROR: adb devices failed.
    exit /b 1
)

(
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" echo %%A
)
) > "%OUT_FILE%"

set /a COUNT=0
for /f "usebackq delims=" %%A in ("%OUT_FILE%") do set /a COUNT+=1

echo.
echo Devices detected: !COUNT!
echo Device list saved to: "%OUT_FILE%"

if !COUNT! LEQ 0 (
    echo ERROR: No authorized Android devices found ^(state "device"^). Unauthorized/offline/recovery/sideload are excluded.
    exit /b 1
)
exit /b 0