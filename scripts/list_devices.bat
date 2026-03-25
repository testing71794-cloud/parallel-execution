@echo off
setlocal EnableExtensions EnableDelayedExpansion

if exist detected_devices.txt del /q detected_devices.txt >nul 2>&1

echo =========================
echo Connected Android devices
echo =========================
adb devices
echo.

set /a DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        echo %%A>> detected_devices.txt
    )
)

echo Total connected devices: !DEVICE_COUNT!
if !DEVICE_COUNT! EQU 0 (
    echo ERROR: No connected Android devices found.
    exit /b 1
)

exit /b 0
