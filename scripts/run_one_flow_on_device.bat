@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_NAME=%~2"
set "FLOW_PATH=%~3"
set "DEVICE_ID=%~4"
set "MAESTRO_OVERRIDE=%~5"
set "APP_PACKAGE=%~6"
set "RETRY_FAILED=%~7"

set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "LOG_FILE=%LOG_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.log"

echo Running %FLOW_NAME% on device %DEVICE_ID%

REM ✅ FIX: remove any input redirection, only use output redirection
maestro test "%FLOW_PATH%" --device %DEVICE_ID% > "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo FAILED %FLOW_NAME% on %DEVICE_ID%
    exit /b 1
)

echo PASSED %FLOW_NAME% on %DEVICE_ID%
exit /b 0
