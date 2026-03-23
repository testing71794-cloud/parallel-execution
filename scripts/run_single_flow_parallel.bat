@echo off
REM =============================================================================
REM One flow on ALL connected devices in PARALLEL.
REM When every device finishes THIS flow, the script exits — then the parent
REM runs the next flow (flow1 -> flow2 -> ...). Pure CMD, no PowerShell.
REM =============================================================================
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."
set "FLOW=%~1"
set "SUITE=%~2"

if "%FLOW%"=="" (
    echo ERROR: Flow path not provided.
    exit /b 1
)
if "%SUITE%"=="" (
    echo ERROR: Suite id not provided ^(nonprinting or printing^).
    exit /b 1
)

if not exist "reports\raw\%SUITE%" mkdir "reports\raw\%SUITE%"
if not exist reports\logs mkdir reports\logs
if not exist reports\excel mkdir reports\excel
if not exist reports\pids mkdir reports\pids

REM Maestro on PATH (common Windows install)
where maestro >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.maestro\bin\maestro.cmd" (
        set "PATH=%USERPROFILE%\.maestro\bin;%PATH%"
    )
)

call scripts\collect_devices.bat
if errorlevel 1 exit /b 1

for %%I in ("%FLOW%") do set "FLOW_NAME=%%~nI"
set "ROOT=%CD%"

echo.
echo Running: "%FLOW%"
echo Suite: %SUITE%
echo Flow name: %FLOW_NAME%
echo.

REM Clean old exit markers for this flow only
del /q "reports\pids\exit_%SUITE%_%FLOW_NAME%_*.txt" 2>nul

REM ---- Launch one CMD per device (true parallel) ----
for %%D in (%DEVICES%) do (
    set "TAG=%%D"
    set "TAG=!TAG::=_!"
    set "TAG=!TAG:\=_!"
    set "RUNNER=reports\pids\run_%SUITE%_%FLOW_NAME%_!TAG!.cmd"

    REM Build a small runner so quoting/spaces in FLOW path always work.
    REM XML/log filenames use TAG (safe for Windows); maestro still targets real serial via -d %%D.
    (
        echo @echo off
        echo setlocal
        echo cd /d "%ROOT%"
        echo echo [%%TIME%%] Device %%D - starting maestro...
        echo maestro test "%FLOW%" -d %%D --format junit --output "reports\raw\%SUITE%\%FLOW_NAME%_!TAG!.xml" 1^>^>"reports\logs\%SUITE%_%FLOW_NAME%_!TAG!.log" 2^>^&1
        echo set ERR=%%ERRORLEVEL%%
        echo ^> "reports\pids\exit_%SUITE%_%FLOW_NAME%_!TAG!.txt" ^(echo %%ERR%%^)
        echo endlocal
        echo exit /b 0
    ) > "!RUNNER!"

    echo Starting parallel: device %%D
    start "maestro %%D %FLOW_NAME%" /MIN cmd /c call "!RUNNER!"
)

echo.
echo Waiting until ALL devices finish this flow ^(%FLOW_NAME%^)...

set /a WAIT_SEC=0
set /a MAX_WAIT=7200

:wait_all
REM Do not use TIMEOUT here — Jenkins/agent has no TTY and TIMEOUT prints
REM "Input redirection is not supported". ~2s delay via localhost ping:
ping 127.0.0.1 -n 3 >nul 2>&1
set /a WAIT_SEC+=2
if !WAIT_SEC! GEQ %MAX_WAIT% (
    echo ERROR: Timeout after %MAX_WAIT%s waiting for devices.
    exit /b 1
)

set /a DONE=0
for %%D in (%DEVICES%) do (
    set "TAG=%%D"
    set "TAG=!TAG::=_!"
    set "TAG=!TAG:\=_!"
    if exist "reports\pids\exit_%SUITE%_%FLOW_NAME%_!TAG!.txt" set /a DONE+=1
)

set /a NEED=0
for %%D in (%DEVICES%) do set /a NEED+=1

if !DONE! LSS !NEED! goto wait_all

echo All devices finished flow %FLOW_NAME%.

REM ---- Fail if any device returned non-zero ----
set "ANY_FAIL=0"
for %%D in (%DEVICES%) do (
    set "TAG=%%D"
    set "TAG=!TAG::=_!"
    set "TAG=!TAG:\=_!"
    set "EC="
    for /f "usebackq tokens=* delims=" %%E in ("reports\pids\exit_%SUITE%_%FLOW_NAME%_!TAG!.txt") do set "EC=%%E"
    set "EC=!EC: =!"
    if not "!EC!"=="0" (
        echo FAILED on device %%D ^(exit !EC!^)
        set "ANY_FAIL=1"
    )
)

if "!ANY_FAIL!"=="1" (
    echo ERROR: One or more devices failed for %FLOW_NAME%.
    exit /b 1
)

exit /b 0
