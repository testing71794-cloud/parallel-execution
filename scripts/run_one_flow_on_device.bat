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

echo Running %FLOW_NAME% on %DEVICE_ID% > "%LOG_FILE%"

if /I "%CLEAR_STATE%"=="true" (
    adb -s "%DEVICE_ID%" shell pm clear "%APP_ID%" >> "%LOG_FILE%" 2>&1
)

"%MAESTRO_CMD%" test "%FLOW_PATH%" --device "%DEVICE_ID%" >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=!errorlevel!"

echo exit_code=!RUN_EXIT! > "%STATUS_FILE%"

> "%RESULT_FILE%" (
    echo suite,flow,device,status,exit_code
    if "!RUN_EXIT!"=="0" (
        echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,PASS,!RUN_EXIT!
    ) else (
        echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,FAIL,!RUN_EXIT!
    )
)

exit /b !RUN_EXIT!
