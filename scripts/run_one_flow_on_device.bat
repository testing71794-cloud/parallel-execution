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
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if /I "%SUITE_NAME%"=="printing" (
    set "REPORT_ROOT=reports_printing"
) else (
    set "REPORT_ROOT=reports"
)

set "DEVICE_DIR=%REPORT_ROOT%\%DEVICE_ID%"
set "OUTPUT_DIR=%DEVICE_DIR%\output"
if not exist "%DEVICE_DIR%" mkdir "%DEVICE_DIR%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

set "LOG_FILE=%LOG_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.log"
set "REPORT_FILE=%DEVICE_DIR%\report.xml"
set "STATUS_FILE=%DEVICE_DIR%\%FLOW_NAME%.status"
set "FAIL_MARK=%PROJECT_DIR%\%SUITE_NAME%__%FLOW_NAME%__%DEVICE_ID%.failed"

del /q "%FAIL_MARK%" >nul 2>&1

echo Running %FLOW_NAME% on %DEVICE_ID% > "%LOG_FILE%"

set "MAESTRO_BIN=maestro"
if not "%MAESTRO_OVERRIDE%"=="" set "MAESTRO_BIN=%MAESTRO_OVERRIDE%"

"%MAESTRO_BIN%" test "%FLOW_PATH%" --device %DEVICE_ID% --format junit --output "%REPORT_FILE%" --test-output-dir "%OUTPUT_DIR%" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" if /I "%RETRY_FAILED%"=="true" (
    echo Retrying %FLOW_NAME% on %DEVICE_ID% >> "%LOG_FILE%"
    "%MAESTRO_BIN%" test "%FLOW_PATH%" --device %DEVICE_ID% --format junit --output "%REPORT_FILE%" --test-output-dir "%OUTPUT_DIR%" >> "%LOG_FILE%" 2>&1
    set "EXIT_CODE=%ERRORLEVEL%"
)

if "%EXIT_CODE%"=="0" (
    > "%STATUS_FILE%" echo PASSED
    exit /b 0
) else (
    > "%STATUS_FILE%" echo FAILED
    > "%FAIL_MARK%" echo 1
    > "%PROJECT_DIR%\pipeline_failed.flag" echo 1
    exit /b 1
)
