@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE=%~1"
set "FLOW_PATH=%~2"
set "FLOW_NAME=%~3"
set "DEVICE_ID=%~4"
set "APP_ID=%~5"
set "CLEAR_STATE=%~6"
set "INCLUDE_TAG=%~7"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

if "%SUITE%"=="" (
    echo ERROR: SUITE missing
    exit /b 1
)

if "%FLOW_PATH%"=="" (
    echo ERROR: FLOW_PATH missing
    exit /b 1
)

if "%FLOW_NAME%"=="" (
    echo ERROR: FLOW_NAME missing
    exit /b 1
)

if "%DEVICE_ID%"=="" (
    echo ERROR: DEVICE_ID missing
    exit /b 1
)

if not exist "%FLOW_PATH%" (
    echo ERROR: Flow file not found: %FLOW_PATH%
    exit /b 1
)

if not exist "%REPO_ROOT%\reports" mkdir "%REPO_ROOT%\reports"
if not exist "%REPO_ROOT%\reports\%SUITE%" mkdir "%REPO_ROOT%\reports\%SUITE%"
if not exist "%REPO_ROOT%\reports\%SUITE%\logs" mkdir "%REPO_ROOT%\reports\%SUITE%\logs"
if not exist "%REPO_ROOT%\reports\%SUITE%\results" mkdir "%REPO_ROOT%\reports\%SUITE%\results"

set "LOG_FILE=%REPO_ROOT%\reports\%SUITE%\logs\%FLOW_NAME%_%DEVICE_ID%.log"
set "RESULT_CSV=%REPO_ROOT%\reports\%SUITE%\results\%FLOW_NAME%_%DEVICE_ID%.csv"

if exist "%RESULT_CSV%" del /f /q "%RESULT_CSV%"
> "%RESULT_CSV%" echo suite,flow_name,device_id,status,exit_code,log_file

echo -------------------------------------
echo Running flow: %FLOW_NAME%
echo Device: %DEVICE_ID%
echo Flow path: %FLOW_PATH%
echo Repo root: %REPO_ROOT%
echo Log file: %LOG_FILE%
echo -------------------------------------

set "MAESTRO_CMD=maestro test "%FLOW_PATH%" --device "%DEVICE_ID%""

echo Command: !MAESTRO_CMD!
> "%LOG_FILE%" echo Command: !MAESTRO_CMD!

call !MAESTRO_CMD! >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    set "STATUS=PASS"
) else (
    set "STATUS=FAIL"
)

>> "%RESULT_CSV%" echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS%,%EXIT_CODE%,%LOG_FILE%

echo Result: %STATUS% ^(Exit Code=%EXIT_CODE%^)
exit /b %EXIT_CODE%
