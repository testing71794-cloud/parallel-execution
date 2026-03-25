@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_NAME=%~2"
set "FLOW_PATH=%~3"
set "DEVICE_ID=%~4"
set "MAESTRO_OVERRIDE=%~5"
set "APP_PACKAGE=%~6"
set "RETRY_FAILED=%~7"

set "PROJECT_DIR=%CD%"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "STATUS_DIR=%PROJECT_DIR%\status"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "SAFE_DEVICE_ID=%DEVICE_ID::=_%"
set "SAFE_DEVICE_ID=%SAFE_DEVICE_ID:/=_%"
set "SAFE_DEVICE_ID=%SAFE_DEVICE_ID:\=_%"

if not "%MAESTRO_OVERRIDE%"=="" (
  set "MAESTRO_CMD=%MAESTRO_OVERRIDE%"
) else (
  set "MAESTRO_CMD=maestro"
)

set "LOG_FILE=%LOG_DIR%\%SUITE_NAME%__%FLOW_NAME%__%SAFE_DEVICE_ID%.log"
set "RESULT_FILE=%STATUS_DIR%\%SUITE_NAME%__%FLOW_NAME%__%SAFE_DEVICE_ID%.txt"

echo ===================================== > "%LOG_FILE%"
echo Flow: %FLOW_NAME% >> "%LOG_FILE%"
echo Device: %DEVICE_ID% >> "%LOG_FILE%"
echo ===================================== >> "%LOG_FILE%"

call %MAESTRO_CMD% test "%FLOW_PATH%" --device %DEVICE_ID% >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

> "%RESULT_FILE%" (
  echo suite=%SUITE_NAME%
  echo flow=%FLOW_NAME%
  echo device=%DEVICE_ID%
  echo log=%LOG_FILE%
  echo exit_code=%EXIT_CODE%
)

if "%EXIT_CODE%"=="0" (
  >> "%RESULT_FILE%" echo status=PASS
  exit /b 0
) else (
  >> "%RESULT_FILE%" echo status=FAIL
  exit /b 1
)