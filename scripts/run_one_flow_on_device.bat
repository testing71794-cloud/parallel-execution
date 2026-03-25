@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_NAME=%~2"
set "FLOW_PATH=%~3"
set "DEVICE_ID=%~4"

set "LOG_DIR=logs"
set "STATUS_DIR=status"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "LOG_FILE=%LOG_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.log"
set "RESULT_FILE=%STATUS_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.txt"

echo Running %FLOW_NAME% on %DEVICE_ID%

maestro test "%FLOW_PATH%" --device %DEVICE_ID% > "%LOG_FILE%" 2>&1

set "EXIT_CODE=%ERRORLEVEL%"

(
echo suite=%SUITE_NAME%
echo flow=%FLOW_NAME%
echo device=%DEVICE_ID%
echo status=%EXIT_CODE%
) > "%RESULT_FILE%"

if "%EXIT_CODE%"=="0" exit /b 0
exit /b 1