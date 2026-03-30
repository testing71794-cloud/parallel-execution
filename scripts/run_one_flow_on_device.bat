@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE=%~1"
set "FLOW_PATH=%~2"
set "FLOW_NAME=%~3"
set "DEVICE_ID=%~4"
set "APP_ID=%~5"
set "CLEAR_STATE=%~6"
set "INCLUDE_TAG=%~7"
set "MAESTRO_CMD=%~8"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

if "%SUITE%"=="" exit /b 1
if "%FLOW_PATH%"=="" exit /b 1
if "%FLOW_NAME%"=="" exit /b 1
if "%DEVICE_ID%"=="" exit /b 1
if not exist "%FLOW_PATH%" (
    echo ERROR: Flow file not found: %FLOW_PATH%
    exit /b 1
)

if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"

if not exist "%REPO_ROOT%\reports" mkdir "%REPO_ROOT%\reports"
if not exist "%REPO_ROOT%\reports\%SUITE%" mkdir "%REPO_ROOT%\reports\%SUITE%"
if not exist "%REPO_ROOT%\reports\%SUITE%\logs" mkdir "%REPO_ROOT%\reports\%SUITE%\logs"
if not exist "%REPO_ROOT%\reports\%SUITE%\results" mkdir "%REPO_ROOT%\reports\%SUITE%\results"
if not exist "%REPO_ROOT%\status" mkdir "%REPO_ROOT%\status"

set "LOG_FILE=%REPO_ROOT%\reports\%SUITE%\logs\%FLOW_NAME%_%DEVICE_ID%.log"
set "RESULT_CSV=%REPO_ROOT%\reports\%SUITE%\results\%FLOW_NAME%_%DEVICE_ID%.csv"
set "STATUS_FILE=%REPO_ROOT%\status\%SUITE%__%FLOW_NAME%__%DEVICE_ID%.txt"

if exist "%RESULT_CSV%" del /f /q "%RESULT_CSV%"
if exist "%STATUS_FILE%" del /f /q "%STATUS_FILE%"

> "%RESULT_CSV%" echo suite,flow_name,device_id,status,exit_code,log_file

(
    echo suite=%SUITE%
    echo flow=%FLOW_NAME%
    echo device=%DEVICE_ID%
    echo status=RUNNING
    echo exit_code=
    echo log=%LOG_FILE%
) > "%STATUS_FILE%"

> "%LOG_FILE%" (
    echo =====================================
    echo RUN ONE FLOW ON DEVICE
    echo =====================================
    echo Suite      : %SUITE%
    echo Flow       : %FLOW_NAME%
    echo Device     : %DEVICE_ID%
    echo Flow path  : %FLOW_PATH%
    echo App ID     : %APP_ID%
    echo ClearState : %CLEAR_STATE%
    echo IncludeTag : %INCLUDE_TAG%
    echo Maestro    : %MAESTRO_CMD%
    echo =====================================
)

set "RC=0"
"%MAESTRO_CMD%" test "%FLOW_PATH%" --device "%DEVICE_ID%" >> "%LOG_FILE%" 2>&1
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
    set "STATUS=PASS"
) else (
    set "STATUS=FAIL"
)

>> "%RESULT_CSV%" echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS%,%RC%,%LOG_FILE%
(
    echo suite=%SUITE%
    echo flow=%FLOW_NAME%
    echo device=%DEVICE_ID%
    echo status=%STATUS%
    echo exit_code=%RC%
    echo log=%LOG_FILE%
) > "%STATUS_FILE%"

echo Device=%DEVICE_ID% Flow=%FLOW_NAME% Result=%STATUS% ExitCode=%RC%
exit /b %RC%
