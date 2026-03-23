@echo off
REM =============================================================================
REM One flow on ALL devices in PARALLEL. Waits for exit marker files (one per device).
REM Jenkins: set MAESTRO_CMD to full path to maestro.cmd if the agent user differs
REM from the user who installed Maestro (e.g. SYSTEM vs your login).
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

REM ADB on PATH (Jenkins: set ANDROID_HOME in job env)
if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools" (
    set "PATH=%ANDROID_HOME%\platform-tools;%PATH%"
)

REM Resolve Maestro: job env MAESTRO_CMD ^> %USERPROFILE%\.maestro ^> where maestro
set "M="
if defined MAESTRO_CMD set "M=%MAESTRO_CMD%"
if not defined M if exist "%USERPROFILE%\.maestro\bin\maestro.cmd" set "M=%USERPROFILE%\.maestro\bin\maestro.cmd"
if not defined M (
    where maestro >nul 2>&1
    if not errorlevel 1 for /f "delims=" %%W in ('where maestro 2^>nul') do if not defined M set "M=%%W"
)
if not defined M (
    echo ERROR: maestro not found.
    echo - Install Maestro for THIS Windows user, OR
    echo - Set Jenkins job env MAESTRO_CMD=C:\full\path\to\maestro.cmd
    exit /b 1
)
set "MAESTRO_CMD=!M!"
echo Using Maestro: !MAESTRO_CMD!

call scripts\collect_devices.bat
if errorlevel 1 exit /b 1

for %%I in ("%FLOW%") do set "FLOW_NAME=%%~nI"
set "ROOT=%CD%"

echo.
echo Running: "%FLOW%"
echo Suite: %SUITE%
echo Flow name: %FLOW_NAME%
echo.

del /q "reports\pids\exit_%SUITE%_%FLOW_NAME%_*.txt" 2>nul

REM ---- Per-device runner: reliable exit file + maestro log ----
for %%D in (%DEVICES%) do (
    set "TAG=%%D"
    set "TAG=!TAG::=_!"
    set "TAG=!TAG:\=_!"
    set "RUNNER=reports\pids\run_%SUITE%_%FLOW_NAME%_!TAG!.cmd"
    set "EXITFILE=reports\pids\exit_%SUITE%_%FLOW_NAME%_!TAG!.txt"
    set "KICK=reports\logs\kickoff_%SUITE%_%FLOW_NAME%_!TAG!.log"

    REM Must expand MAESTRO_CMD and ROOT while writing (no broken ^> ^(echo ERR^) lines)
    REM Child cmd may get a minimal PATH under Jenkins — prepend adb; wake screen; verify package.
    (
        echo @echo off
        echo setlocal EnableExtensions
        echo cd /d "%ROOT%"
        echo if defined ANDROID_HOME if exist "%%ANDROID_HOME%%\platform-tools" set "PATH=%%ANDROID_HOME%%\platform-tools;%%PATH%%"
        echo echo [%DATE% %TIME%] kickoff device=%%D ^> "!KICK!"
        echo echo MAESTRO_CMD=!MAESTRO_CMD! ^>^> "!KICK!"
        echo echo FLOW=%FLOW% ^>^> "!KICK!"
        echo echo SESSIONNAME=%%SESSIONNAME%% ^>^> "!KICK!" 2^>^&1
        echo where adb ^>^> "!KICK!" 2^>^&1
        echo adb -s %%D shell echo device_ok ^>^> "!KICK!" 2^>^&1
        echo adb -s %%D shell input keyevent 224 ^>^> "!KICK!" 2^>^&1
        echo adb -s %%D shell pm path com.kodaksmile ^>^> "!KICK!" 2^>^&1
        echo if not exist "reports\logs\debug_%SUITE%_%FLOW_NAME%_!TAG!" mkdir "reports\logs\debug_%SUITE%_%FLOW_NAME%_!TAG!"
        REM Official CLI: global --device before test; --config so workspace matches repo root (runFlow paths^)
        echo call "!MAESTRO_CMD!" --device %%D test "%FLOW%" --config "%ROOT%\config.yaml" --format junit --output "reports\raw\%SUITE%\%FLOW_NAME%_!TAG!.xml" --debug-output "reports\logs\debug_%SUITE%_%FLOW_NAME%_!TAG!" 1^>^>"reports\logs\%SUITE%_%FLOW_NAME%_!TAG!.log" 2^>^&1
        echo set ERR=%%ERRORLEVEL%%
        echo ^(echo %%ERR%%^)^> "!EXITFILE!"
    ) > "!RUNNER!"

    echo Starting parallel: device %%D
    start "maestro %%D %FLOW_NAME%" /MIN cmd /c call "!RUNNER!"
)

echo.
echo Waiting until ALL devices finish this flow ^(%FLOW_NAME%^)...
echo If this hangs: open reports\logs\kickoff_*.log and the flow log for each device.
echo.

set /a WAIT_SEC=0
set /a MAX_WAIT=7200

:wait_all
ping 127.0.0.1 -n 3 >nul 2>&1
set /a WAIT_SEC+=2
if !WAIT_SEC! GEQ %MAX_WAIT% (
    echo ERROR: Timeout after %MAX_WAIT%s — exit markers missing. Check kickoff logs and maestro logs under reports\logs\
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

REM Heartbeat every ~30s
set /a "HB=!WAIT_SEC! %% 30"
if "!HB!"=="0" if !WAIT_SEC! GTR 0 (
    echo ... still waiting !DONE!/!NEED! devices ^(!WAIT_SEC!s^)
)

if !DONE! LSS !NEED! goto wait_all

echo All devices finished flow %FLOW_NAME%.

set "ANY_FAIL=0"
for %%D in (%DEVICES%) do (
    set "TAG=%%D"
    set "TAG=!TAG::=_!"
    set "TAG=!TAG:\=_!"
    set "EC="
    for /f "usebackq tokens=* delims=" %%E in ("reports\pids\exit_%SUITE%_%FLOW_NAME%_!TAG!.txt") do set "EC=%%E"
    set "EC=!EC: =!"
    if not "!EC!"=="0" (
        echo FAILED on device %%D ^(exit !EC!^) - see reports\logs\%SUITE%_%FLOW_NAME%_!TAG!.log
        set "ANY_FAIL=1"
    )
)

if "!ANY_FAIL!"=="1" (
    echo ERROR: One or more devices failed for %FLOW_NAME%.
    exit /b 1
)

exit /b 0
