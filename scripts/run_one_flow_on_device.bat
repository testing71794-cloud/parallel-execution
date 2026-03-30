@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Args:
REM %1 = SUITE
REM %2 = FLOW_PATH
REM %3 = DEVICE_ID
REM %4 = APP_ID
REM %5 = CLEAR_STATE
REM %6 = MAESTRO_CMD

set "SUITE=%~1"
set "FLOW_PATH=%~2"
set "DEVICE_ID=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"

if "%SUITE%"=="" exit /b 10
if "%FLOW_PATH%"=="" exit /b 11
if "%DEVICE_ID%"=="" exit /b 12
if "%APP_ID%"=="" exit /b 13
if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

for %%I in ("%FLOW_PATH%") do set "FLOW_NAME=%%~nI"

set "LOG_DIR=%REPO_ROOT%\reports\%SUITE%\logs"
set "RESULT_DIR=%REPO_ROOT%\reports\%SUITE%\results"
set "STATUS_DIR=%REPO_ROOT%\status"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "LOG_FILE=%LOG_DIR%\%FLOW_NAME%_%DEVICE_ID%.log"
set "RESULT_FILE=%RESULT_DIR%\%FLOW_NAME%_%DEVICE_ID%.csv"
set "STATUS_FILE=%STATUS_DIR%\%SUITE%__%FLOW_NAME%__%DEVICE_ID%.txt"

(
echo =====================================
echo RUN ONE FLOW ON DEVICE
echo =====================================
echo Timestamp   : %date% %time%
echo Suite       : %SUITE%
echo Flow path   : %FLOW_PATH%
echo Flow name   : %FLOW_NAME%
echo Device      : %DEVICE_ID%
echo App id      : %APP_ID%
echo Clear state : %CLEAR_STATE%
echo Maestro cmd : %MAESTRO_CMD%
echo Repo root   : %REPO_ROOT%
echo Log file    : %LOG_FILE%
echo Result file : %RESULT_FILE%
echo Status file : %STATUS_FILE%
echo =====================================
) > "%LOG_FILE%"

if not exist "%FLOW_PATH%" (
    echo ERROR: Flow file not found: %FLOW_PATH%>> "%LOG_FILE%"
    > "%STATUS_FILE%" (
        echo suite=%SUITE%
        echo flow=%FLOW_NAME%
        echo device=%DEVICE_ID%
        echo status=FAIL
        echo exit_code=20
        echo reason=FLOW_NOT_FOUND
    )
    > "%RESULT_FILE%" (
        echo suite,flow,device,status,exit_code,reason,log_file
        echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,FAIL,20,FLOW_NOT_FOUND,"%LOG_FILE%"
    )
    exit /b 20
)

where adb >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: adb not found in PATH>> "%LOG_FILE%"
    > "%STATUS_FILE%" (
        echo suite=%SUITE%
        echo flow=%FLOW_NAME%
        echo device=%DEVICE_ID%
        echo status=FAIL
        echo exit_code=21
        echo reason=ADB_NOT_FOUND
    )
    > "%RESULT_FILE%" (
        echo suite,flow,device,status,exit_code,reason,log_file
        echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,FAIL,21,ADB_NOT_FOUND,"%LOG_FILE%"
    )
    exit /b 21
)

where "%MAESTRO_CMD%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo WARNING: Maestro command not found via WHERE: %MAESTRO_CMD%>> "%LOG_FILE%"
    echo Continuing anyway...>> "%LOG_FILE%"
)

adb -s "%DEVICE_ID%" get-state >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Device is not reachable via adb: %DEVICE_ID%>> "%LOG_FILE%"
    > "%STATUS_FILE%" (
        echo suite=%SUITE%
        echo flow=%FLOW_NAME%
        echo device=%DEVICE_ID%
        echo status=FAIL
        echo exit_code=22
        echo reason=DEVICE_NOT_READY
    )
    > "%RESULT_FILE%" (
        echo suite,flow,device,status,exit_code,reason,log_file
        echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,FAIL,22,DEVICE_NOT_READY,"%LOG_FILE%"
    )
    exit /b 22
)

if /I "%CLEAR_STATE%"=="true" (
    echo Clearing app state...>> "%LOG_FILE%"
    adb -s "%DEVICE_ID%" shell pm clear "%APP_ID%" >> "%LOG_FILE%" 2>&1
    echo Clear-state exit code: !errorlevel!>> "%LOG_FILE%"
)

echo Starting Maestro test...>> "%LOG_FILE%"
echo Command: %MAESTRO_CMD% test "%FLOW_PATH%" --device "%DEVICE_ID%">> "%LOG_FILE%"
"%MAESTRO_CMD%" test "%FLOW_PATH%" --device "%DEVICE_ID%" >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=!errorlevel!"

if "!RUN_EXIT!"=="0" (
    set "STATUS_VALUE=PASS"
    set "REASON=OK"
) else (
    set "STATUS_VALUE=FAIL"
    set "REASON=MAESTRO_FAILED"
)

> "%STATUS_FILE%" (
    echo suite=%SUITE%
    echo flow=%FLOW_NAME%
    echo device=%DEVICE_ID%
    echo app_id=%APP_ID%
    echo clear_state=%CLEAR_STATE%
    echo maestro_cmd=%MAESTRO_CMD%
    echo status=!STATUS_VALUE!
    echo exit_code=!RUN_EXIT!
    echo reason=!REASON!
)

> "%RESULT_FILE%" (
    echo suite,flow,device,status,exit_code,reason,log_file
    echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,!STATUS_VALUE!,!RUN_EXIT!,!REASON!,"%LOG_FILE%"
)

echo Final exit code: !RUN_EXIT!>> "%LOG_FILE%"
exit /b !RUN_EXIT!
