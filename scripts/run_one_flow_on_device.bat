@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Args:
REM %1 = SUITE
REM %2 = FLOW_PATH
REM %3 = DEVICE_ID
REM %4 = APP_ID
REM %5 = CLEAR_STATE
REM %6 = MAESTRO_CMD
REM %7 = INCLUDE_TAG (optional)

set "SUITE=%~1"
set "FLOW_PATH=%~2"
set "DEVICE_ID=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"
set "INCLUDE_TAG=%~7"

if "%SUITE%"=="" exit /b 10
if "%FLOW_PATH%"=="" exit /b 11
if "%DEVICE_ID%"=="" exit /b 12
if "%APP_ID%"=="" exit /b 13
if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"
if "%INCLUDE_TAG%"=="__EMPTY__" set "INCLUDE_TAG="

set "CLASSPATH="
set "JAVA_TOOL_OPTIONS="
set "_JAVA_OPTIONS="
set "JDK_JAVA_OPTIONS="

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

call "%REPO_ROOT%\scripts\set_maestro_java.bat" "%MAESTRO_CMD%"
if errorlevel 1 exit /b 14

if exist "%MAESTRO_HOME%\maestro.bat" (
    set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.bat"
) else if exist "%MAESTRO_HOME%\maestro.cmd" (
    set "MAESTRO_BIN=%MAESTRO_HOME%\maestro.cmd"
) else (
    set "MAESTRO_BIN=%MAESTRO_CMD%"
)

for %%I in ("%FLOW_PATH%") do set "FLOW_NAME=%%~nI"

set "REPORT_ROOT=%REPO_ROOT%\reports\%SUITE%"
set "LOG_DIR=%REPORT_ROOT%\logs"
set "RESULT_DIR=%REPORT_ROOT%\results"
set "STATUS_DIR=%REPO_ROOT%\status"

if not exist "%REPORT_ROOT%" mkdir "%REPORT_ROOT%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "SAFE_FLOW=%FLOW_NAME: =_%"
set "SAFE_DEVICE=%DEVICE_ID: =_%"
set "LOG_FILE=%LOG_DIR%\%SAFE_FLOW%_%SAFE_DEVICE%.log"
set "RESULT_FILE=%RESULT_DIR%\%SAFE_FLOW%_%SAFE_DEVICE%.csv"
set "STATUS_FILE=%STATUS_DIR%\%SUITE%__%SAFE_FLOW%__%SAFE_DEVICE%.txt"

(
echo =====================================
echo RUN ONE FLOW ON DEVICE
echo =====================================
echo Timestamp        : %date% %time%
echo Suite            : %SUITE%
echo Flow path        : %FLOW_PATH%
echo Flow name        : %FLOW_NAME%
echo Device           : %DEVICE_ID%
echo App id           : %APP_ID%
echo Clear state      : %CLEAR_STATE%
echo Include tag      : %INCLUDE_TAG%
echo JAVA_HOME        : %JAVA_HOME%
echo MAESTRO_HOME     : %MAESTRO_HOME%
echo Maestro cmd      : %MAESTRO_BIN%
echo =====================================
) > "%LOG_FILE%"

where java >> "%LOG_FILE%" 2>&1
java -version >> "%LOG_FILE%" 2>&1
where adb >> "%LOG_FILE%" 2>&1
where maestro >> "%LOG_FILE%" 2>&1
where maestro.bat >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

set "RUN_EXIT=0"
set "STATUS_VALUE=PASS"
set "REASON=OK"

if not exist "%FLOW_PATH%" (
    echo ERROR: Flow file not found: %FLOW_PATH%>> "%LOG_FILE%"
    set "RUN_EXIT=20"
    set "STATUS_VALUE=FAIL"
    set "REASON=FLOW_FILE_NOT_FOUND"
    goto :write_result
)

adb -s "%DEVICE_ID%" get-state >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Device not ready: %DEVICE_ID%>> "%LOG_FILE%"
    set "RUN_EXIT=22"
    set "STATUS_VALUE=FAIL"
    set "REASON=DEVICE_NOT_READY"
    goto :write_result
)

if /I "%CLEAR_STATE%"=="true" (
    echo Clearing app state...>> "%LOG_FILE%"
    adb -s "%DEVICE_ID%" shell pm clear "%APP_ID%" >> "%LOG_FILE%" 2>&1
    echo Clear-state exit code: !errorlevel!>> "%LOG_FILE%"
)

set "MAESTRO_ARGS=test "%FLOW_PATH%" --device "%DEVICE_ID%""
if not "%INCLUDE_TAG%"=="" set "MAESTRO_ARGS=%MAESTRO_ARGS% --include-tags "%INCLUDE_TAG%""

echo Starting Maestro test...>> "%LOG_FILE%"
echo Command: call "%MAESTRO_BIN%" !MAESTRO_ARGS!>> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

call "%MAESTRO_BIN%" !MAESTRO_ARGS! >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=%ERRORLEVEL%"
if not "%RUN_EXIT%"=="0" (
    set "STATUS_VALUE=FAIL"
    set "REASON=MAESTRO_FAILED"
)

:write_result
if not defined DEVICE_NAME (
  for /f "delims=" %%N in ('python "%REPO_ROOT%\scripts\resolve_device_name.py" "%DEVICE_ID%" 2^>nul') do set "DEVICE_NAME=%%N"
)
if not defined DEVICE_NAME set "DEVICE_NAME=%DEVICE_ID%"
> "%STATUS_FILE%" (
    echo suite=%SUITE%
    echo flow=%FLOW_NAME%
    echo device=%DEVICE_ID%
    echo device_id=%DEVICE_ID%
    echo device_name=%DEVICE_NAME%
    echo status=%STATUS_VALUE%
    echo exit_code=%RUN_EXIT%
    echo reason=%REASON%
    echo log_file=%LOG_FILE%
    echo first_log_path=%LOG_FILE%
    echo log_path=%LOG_FILE%
    echo retry_count=0
    echo timestamp=%date% %time%
)

> "%RESULT_FILE%" (
    echo suite,flow,device,status,exit_code,reason,log_file
    echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS_VALUE%,%RUN_EXIT%,%REASON%,"%LOG_FILE%"
)

echo. >> "%LOG_FILE%"
echo Final status   : %STATUS_VALUE%>> "%LOG_FILE%"
echo Final reason   : %REASON%>> "%LOG_FILE%"
echo Final exit code: %RUN_EXIT%>> "%LOG_FILE%"
exit /b %RUN_EXIT%
