@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Args:
REM %1 = SUITE
REM %2 = FLOW_DIR
REM %3 = INCLUDE_TAG
REM %4 = APP_ID
REM %5 = CLEAR_STATE
REM %6 = MAESTRO_CMD

set "SUITE=%~1"
set "FLOW_DIR=%~2"
set "INCLUDE_TAG=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"

if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "FLOW_ROOT=%REPO_ROOT%\%FLOW_DIR%"
set "RUNNER_BAT=%REPO_ROOT%\scripts\run_one_flow_on_device.bat"

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo.
echo Suite: %SUITE%
echo Flow dir: %FLOW_DIR%
echo Include tag: %INCLUDE_TAG%
echo App id: %APP_ID%
echo Clear state: %CLEAR_STATE%
echo Maestro cmd: %MAESTRO_CMD%
echo.
echo Repo root: %REPO_ROOT%
echo Flow root: %FLOW_ROOT%
echo Runner bat: %RUNNER_BAT%
echo.

if not exist "%RUNNER_BAT%" (
    echo ERROR: Runner bat not found
    exit /b 30
)

if not exist "%FLOW_ROOT%" (
    echo ERROR: Flow folder not found: %FLOW_ROOT%
    exit /b 31
)

set "TMP_DEVICES=%TEMP%\devices_%RANDOM%_%RANDOM%.txt"
adb devices | findstr /R /C:".*	device$" > "%TMP_DEVICES%"
if errorlevel 1 (
    echo ERROR: No connected devices found
    if exist "%TMP_DEVICES%" del /q "%TMP_DEVICES%" 2>nul
    exit /b 32
)

echo Devices found:
for /f %%D in (%TMP_DEVICES%) do echo  - %%D
echo.

set "ANY_FAIL=0"
set "ANY_RESULT=0"

for %%F in ("%FLOW_ROOT%\*.yaml") do (
    set "FLOW_PATH=%%~fF"
    set "FLOW_NAME=%%~nF"

    echo =====================================
    echo Running !FLOW_NAME! on all devices
    echo =====================================

    for /f %%D in (%TMP_DEVICES%) do (
        call "%RUNNER_BAT%" "%SUITE%" "!FLOW_PATH!" "%%D" "%APP_ID%" "%CLEAR_STATE%" "%MAESTRO_CMD%"
        set "RUN_EXIT=!ERRORLEVEL!"

        set "STATUS_FILE=%REPO_ROOT%\status\%SUITE%__!FLOW_NAME!__%%D.txt"
        set "RESULT_FILE=%REPO_ROOT%\reports\%SUITE%\results\!FLOW_NAME!_%%D.csv"
        set "LOG_FILE=%REPO_ROOT%\reports\%SUITE%\logs\!FLOW_NAME!_%%D.log"

        set "ARTIFACTS_OK=False"
        if exist "!STATUS_FILE!" if exist "!RESULT_FILE!" if exist "!LOG_FILE!" set "ARTIFACTS_OK=True"
        if exist "!RESULT_FILE!" set "ANY_RESULT=1"

        echo Device %%D -^> ExitCode !RUN_EXIT! -^> ArtifactsOk !ARTIFACTS_OK!

        if not "!RUN_EXIT!"=="0" set "ANY_FAIL=1"
        if /I not "!ARTIFACTS_OK!"=="True" set "ANY_FAIL=1"
    )
    echo.
)

echo =====================================
echo Merging per-device result files
echo =====================================

set "MERGED_CSV=%REPO_ROOT%\reports\%SUITE%\all_results.csv"
if exist "%MERGED_CSV%" del /q "%MERGED_CSV%" 2>nul

set "HEADER_WRITTEN=0"
for %%R in ("%REPO_ROOT%\reports\%SUITE%\results\*.csv") do (
    if "!HEADER_WRITTEN!"=="0" (
        type "%%~fR" > "%MERGED_CSV%"
        set "HEADER_WRITTEN=1"
    ) else (
        powershell -NoProfile -Command "Get-Content -Path '%%~fR' | Select-Object -Skip 1" >> "%MERGED_CSV%"
    )
)

if "!ANY_RESULT!"=="0" (
    echo ERROR: No per-device result CSV files were produced for suite %SUITE%
    set "ANY_FAIL=1"
)

echo.
echo =====================================
echo FINAL RESULT FOR SUITE %SUITE% = !ANY_FAIL!
echo =====================================

if exist "%TMP_DEVICES%" del /q "%TMP_DEVICES%" 2>nul
exit /b !ANY_FAIL!
