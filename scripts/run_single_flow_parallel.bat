@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."
set "FLOW=%~1"

if "%FLOW%"=="" (
    echo ERROR: Flow path not provided.
    exit /b 1
)

if not exist reports\raw mkdir reports\raw
if not exist reports\logs mkdir reports\logs
if not exist reports\excel mkdir reports\excel
if not exist reports\pids mkdir reports\pids

call scripts\collect_devices.bat
if errorlevel 1 exit /b 1

for %%I in ("%FLOW%") do set "FLOW_NAME=%%~nI"

echo Running flow: %FLOW%
echo.

for %%D in (%DEVICES%) do (
    echo Starting on device: %%D
    start "maestro_%%D_%FLOW_NAME%" /B cmd /c "maestro test "%FLOW%" -d %%D --format junit --output "reports\raw\%FLOW_NAME%_%%D.xml" 1>"reports\logs\%FLOW_NAME%_%%D.log" 2>&1"
)

echo.
echo Waiting for all devices to finish %FLOW% ...

:wait_loop
timeout /t 2 /nobreak >nul
set "RUNNING_COUNT=0"
for %%D in (%DEVICES%) do (
    tasklist /v /fo csv | findstr /i /c:"maestro_%%D_%FLOW_NAME%" >nul
    if not errorlevel 1 set /a RUNNING_COUNT+=1
)
if not "%RUNNING_COUNT%"=="0" goto wait_loop

echo All devices finished for %FLOW%
exit /b 0
