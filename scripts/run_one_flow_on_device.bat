@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

call "%SCRIPT_DIR%set_maestro_java.bat" || exit /b 1

set "SUITE=%~1"
set "FLOW_PATH=%~2"
set "FLOW_NAME=%~3"
set "DEVICE_ID=%~4"
set "APP_ID=%~5"
set "CLEAR_STATE=%~6"
set "INCLUDE_TAG=%~7"
set "MAESTRO_CMD=%~8"

if /I "%INCLUDE_TAG%"=="__EMPTY__" set "INCLUDE_TAG="
if /I "%MAESTRO_CMD%"=="__EMPTY__" set "MAESTRO_CMD="
if not defined MAESTRO_CMD set "MAESTRO_CMD=maestro"
if not defined CLEAR_STATE set "CLEAR_STATE=true"

if "%SUITE%"=="" exit /b 1
if "%FLOW_PATH%"=="" exit /b 1
if "%FLOW_NAME%"=="" exit /b 1
if "%DEVICE_ID%"=="" exit /b 1

set "REPORTS_DIR=%REPO_ROOT%\reports\%SUITE%"
set "LOG_DIR=%REPORTS_DIR%\logs"
set "RESULTS_DIR=%REPORTS_DIR%\results"
set "STATUS_DIR=%REPO_ROOT%\status"

if not exist "%REPORTS_DIR%" mkdir "%REPORTS_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "SAFE_FLOW=%FLOW_NAME: =_%"
set "SAFE_DEVICE=%DEVICE_ID: =_%"
set "LOG_FILE=%LOG_DIR%\%SAFE_FLOW%_%SAFE_DEVICE%.log"
set "RESULT_FILE=%RESULTS_DIR%\%SAFE_FLOW%_%SAFE_DEVICE%.csv"
set "STATUS_FILE=%STATUS_DIR%\%SUITE%__%SAFE_FLOW%__%SAFE_DEVICE%.txt"

> "%LOG_FILE%" echo =====================================
>>"%LOG_FILE%" echo RUN ONE FLOW ON DEVICE
>>"%LOG_FILE%" echo =====================================
>>"%LOG_FILE%" echo Repo Root  : %REPO_ROOT%
>>"%LOG_FILE%" echo Suite      : %SUITE%
>>"%LOG_FILE%" echo Flow Name  : %FLOW_NAME%
>>"%LOG_FILE%" echo Flow Path  : %FLOW_PATH%
>>"%LOG_FILE%" echo Device     : %DEVICE_ID%
>>"%LOG_FILE%" echo App Id     : %APP_ID%
>>"%LOG_FILE%" echo ClearState : %CLEAR_STATE%
>>"%LOG_FILE%" echo IncludeTag : %INCLUDE_TAG%
>>"%LOG_FILE%" echo MaestroCmd : %MAESTRO_CMD%
>>"%LOG_FILE%" echo =====================================
>>"%LOG_FILE%" echo.
>>"%LOG_FILE%" echo JAVA_HOME=%JAVA_HOME%
where java >>"%LOG_FILE%" 2>&1
java -version >>"%LOG_FILE%" 2>&1
where maestro >>"%LOG_FILE%" 2>&1
maestro --version >>"%LOG_FILE%" 2>&1
>>"%LOG_FILE%" echo.
>>"%LOG_FILE%" echo ===== ADB DEVICE CHECK =====
adb -s "%DEVICE_ID%" get-state >>"%LOG_FILE%" 2>&1

set "STATUS=FAIL"
set "EXIT_CODE=1"

> "%STATUS_FILE%" echo suite=%SUITE%
>>"%STATUS_FILE%" echo flow=%FLOW_NAME%
>>"%STATUS_FILE%" echo device=%DEVICE_ID%
>>"%STATUS_FILE%" echo status=RUNNING
>>"%STATUS_FILE%" echo exit_code=
>>"%STATUS_FILE%" echo log=%LOG_FILE%

pushd "%REPO_ROOT%" >nul
>>"%LOG_FILE%" echo ===== EXECUTING =====
>>"%LOG_FILE%" echo %MAESTRO_CMD% --device "%DEVICE_ID%" test "%FLOW_PATH%"
call %MAESTRO_CMD% --device "%DEVICE_ID%" test "%FLOW_PATH%" >>"%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul

if exist "%LOG_FILE%" (
    for %%A in ("%LOG_FILE%") do set "LOG_SIZE=%%~zA"
) else (
    set "LOG_SIZE=0"
)

if "%EXIT_CODE%"=="0" (
    if not "%LOG_SIZE%"=="0" (
        set "STATUS=PASS"
    ) else (
        set "STATUS=FAIL"
        set "EXIT_CODE=9001"
        >>"%LOG_FILE%" echo ERROR: Maestro returned success but log file is empty.
    )
) else (
    set "STATUS=FAIL"
)

> "%STATUS_FILE%" echo suite=%SUITE%
>>"%STATUS_FILE%" echo flow=%FLOW_NAME%
>>"%STATUS_FILE%" echo device=%DEVICE_ID%
>>"%STATUS_FILE%" echo status=%STATUS%
>>"%STATUS_FILE%" echo exit_code=%EXIT_CODE%
>>"%STATUS_FILE%" echo log=%LOG_FILE%

> "%RESULT_FILE%" echo suite,flow_name,device_id,status,exit_code,log_file
>>"%RESULT_FILE%" echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS%,%EXIT_CODE%,%LOG_FILE%

if not exist "%STATUS_FILE%" (
    echo ERROR: status file was not created
    exit /b 9101
)
if not exist "%RESULT_FILE%" (
    echo ERROR: result file was not created
    exit /b 9102
)
if not exist "%LOG_FILE%" (
    echo ERROR: log file was not created
    exit /b 9103
)

if /I "%STATUS%"=="PASS" (
    echo PASS: %FLOW_NAME% on %DEVICE_ID%
    exit /b 0
) else (
    echo FAIL: %FLOW_NAME% on %DEVICE_ID% with exit code %EXIT_CODE%
    exit /b %EXIT_CODE%
)
