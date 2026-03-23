@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "DEVICES="
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" (
        set "DEVICES=!DEVICES! %%A"
    )
)

if "%DEVICES%"=="" (
    echo ERROR: No connected Android devices found.
    endlocal & exit /b 1
)

endlocal & set "DEVICES=%DEVICES%"
exit /b 0
