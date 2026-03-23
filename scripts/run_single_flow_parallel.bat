@echo off
setlocal enabledelayedexpansion

set FLOW=%~1
set SUITE=%~2
set FLOWNAME=%~n1

if "%FLOW%"=="" exit /b 1
if "%SUITE%"=="" set SUITE=nonprinting

echo.
echo Running: "%FLOW%"
echo Suite: %SUITE%
echo Flow name: %FLOWNAME%
echo.

if not exist reports\raw mkdir reports\raw
if not exist reports\logs mkdir reports\logs
if not exist reports\state mkdir reports\state

del /q reports\state\%FLOWNAME%_*.done 2>nul
del /q reports\state\%FLOWNAME%_*.exit 2>nul

set DEVICES=
for /f "skip=1 tokens=1" %%D in ('adb devices') do (
    if not "%%D"=="" if not "%%D"=="List" set DEVICES=!DEVICES! %%D
)

for %%D in (%DEVICES%) do (
    echo Starting parallel: device %%D
    start "" cmd /c call scripts\run_one_device_flow.bat "%%D" "%FLOW%" "%SUITE%" "%FLOWNAME%"
)

echo.
echo Waiting until ALL devices finish this flow (%FLOWNAME%)...

:wait_loop
set ALL_DONE=1
for %%D in (%DEVICES%) do (
    if not exist reports\state\%FLOWNAME%_%%D.done set ALL_DONE=0
)

if "%ALL_DONE%"=="1" goto done

timeout /t 2 >nul
goto wait_loop

:done
echo All devices finished for %FLOWNAME%.
exit /b 0
