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
if "%AUTOFILL_RESTORE_AFTER_TEST%"=="" set "AUTOFILL_RESTORE_AFTER_TEST=0"
set "ORIG_AUTOFILL_SERVICE=unknown"

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

echo.>> "%LOG_FILE%"
echo [INFO] Device %DEVICE_ID% - checking autofill service>> "%LOG_FILE%"
for /f "delims=" %%A in ('adb -s "%DEVICE_ID%" shell settings get secure autofill_service 2^>^&1') do (
    if not defined ORIG_AUTOFILL_SERVICE_RESULT set "ORIG_AUTOFILL_SERVICE_RESULT=%%A"
)
if defined ORIG_AUTOFILL_SERVICE_RESULT set "ORIG_AUTOFILL_SERVICE=!ORIG_AUTOFILL_SERVICE_RESULT!"
echo [INFO] Device %DEVICE_ID% - autofill_service before change: !ORIG_AUTOFILL_SERVICE!>> "%LOG_FILE%"
adb -s "%DEVICE_ID%" shell settings put secure autofill_service null >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [WARN] Device %DEVICE_ID% - could not disable autofill_service, continuing>> "%LOG_FILE%"
) else (
    echo [INFO] Device %DEVICE_ID% - autofill disabled ^(autofill_service=null^)>> "%LOG_FILE%"
)

for %%P in (com.samsung.android.samsungpassautofill com.samsung.android.authfw) do (
    adb -s "%DEVICE_ID%" shell cmd package disable-user --user 0 %%P >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo [WARN] Device %DEVICE_ID% - Samsung package not disabled/supported: %%P>> "%LOG_FILE%"
    ) else (
        echo [INFO] Device %DEVICE_ID% - Samsung package disabled: %%P>> "%LOG_FILE%"
    )
)

if /I "%CLEAR_STATE%"=="true" (
    echo Clearing app state...>> "%LOG_FILE%"
    adb -s "%DEVICE_ID%" shell pm clear "%APP_ID%" >> "%LOG_FILE%" 2>&1
    echo Clear-state exit code: !errorlevel!>> "%LOG_FILE%"
)

set "SIGNUP_RETRY_USED=0"
if /I not "%FLOW_NAME%"=="flow1b" goto :run_maestro_default
rem ---- flow1b block (see end of file for :run_maestro_default) ----

rem ---- flow1b: unique email per device + optional duplicate-user retry (parallel-safe JSON per device) ----
set "SIGNUP_BAT=%TEMP%\kodak_signup_!SAFE_DEVICE!_!RANDOM!.bat"
python "%REPO_ROOT%\scripts\generate_signup_user.py" --device "%DEVICE_ID%" --repo "%REPO_ROOT%" --json-basename "%SAFE_DEVICE%" --write-bat "!SIGNUP_BAT!"
if errorlevel 1 (
    echo ERROR: generate_signup_user.py failed>> "%LOG_FILE%"
    set "RUN_EXIT=30"
    set "STATUS_VALUE=FAIL"
    set "REASON=SIGNUP_USER_GEN_FAILED"
    goto :write_result
)
call "!SIGNUP_BAT!"
set "KODAK_SIGNUP_JSON=%REPO_ROOT%\reports\signup_users\%SAFE_DEVICE%_signup_user.json"
echo.>> "%LOG_FILE%"
echo === Signup user (flow1b) ===>> "%LOG_FILE%"
echo KODAK_SIGNUP_EMAIL=!EMAIL!>> "%LOG_FILE%"
echo KODAK_SIGNUP_RUN_ID=!SIGNUP_RUN_ID!>> "%LOG_FILE%"
echo KODAK_SIGNUP_ATTEMPT=!SIGNUP_ATTEMPT!>> "%LOG_FILE%"
if defined KODAK_SIGNUP_JSON echo KODAK_SIGNUP_JSON=!KODAK_SIGNUP_JSON!>> "%LOG_FILE%"

set "MAESTRO_ARGS=test -e EMAIL=!EMAIL! -e FULL_NAME=!FULL_NAME! -e PASSWORD=!PASSWORD!"
set "MAESTRO_ARGS=!MAESTRO_ARGS! "%FLOW_PATH%""
set "MAESTRO_ARGS=!MAESTRO_ARGS! --device "%DEVICE_ID%""
if not "%INCLUDE_TAG%"=="" set "MAESTRO_ARGS=!MAESTRO_ARGS! --include-tags "%INCLUDE_TAG%""

echo Starting Maestro test (flow1b)...>> "%LOG_FILE%"
echo Command: call "%MAESTRO_BIN%" !MAESTRO_ARGS!>> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
call "%MAESTRO_BIN%" !MAESTRO_ARGS! >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=%ERRORLEVEL%"
if "!RUN_EXIT!"=="0" goto :after_flow1b_maestro

python "%REPO_ROOT%\scripts\check_signup_duplicate_log.py" "%LOG_FILE%" 1>>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    set "STATUS_VALUE=FAIL"
    set "REASON=MAESTRO_FAILED"
    goto :after_flow1b_maestro
)
echo Duplicate-like signup error detected; regenerating user and retrying once...>> "%LOG_FILE%"
python "%REPO_ROOT%\scripts\generate_signup_user.py" --device "%DEVICE_ID%" --repo "%REPO_ROOT%" --json-basename "%SAFE_DEVICE%" --retry --write-bat "!SIGNUP_BAT!"
if errorlevel 1 (
    set "STATUS_VALUE=FAIL"
    set "REASON=SIGNUP_RETRY_GEN_FAILED"
    set "RUN_EXIT=31"
    goto :write_result
)
call "!SIGNUP_BAT!"
set "SIGNUP_RETRY_USED=1"
echo KODAK_SIGNUP_EMAIL_RETRY=!EMAIL!>> "%LOG_FILE%"
echo.>> "%LOG_FILE%"
echo === Maestro retry (flow1b) ===>> "%LOG_FILE%"
set "MAESTRO_ARGS=test -e EMAIL=!EMAIL! -e FULL_NAME=!FULL_NAME! -e PASSWORD=!PASSWORD!"
set "MAESTRO_ARGS=!MAESTRO_ARGS! "%FLOW_PATH%""
set "MAESTRO_ARGS=!MAESTRO_ARGS! --device "%DEVICE_ID%""
if not "%INCLUDE_TAG%"=="" set "MAESTRO_ARGS=!MAESTRO_ARGS! --include-tags "%INCLUDE_TAG%""
call "%MAESTRO_BIN%" !MAESTRO_ARGS! >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=%ERRORLEVEL%"
if "!RUN_EXIT!"=="0" (
    set "STATUS_VALUE=FLAKY"
    set "REASON=SIGNUP_DUPLICATE_RETRY"
) else (
    set "STATUS_VALUE=FAIL"
    set "REASON=MAESTRO_FAILED"
)
goto :after_flow1b_maestro

:run_maestro_default
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

:after_flow1b_maestro

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
    echo retry_count=!SIGNUP_RETRY_USED!
    echo timestamp=%date% %time%
)
if /I "%FLOW_NAME%"=="flow1b" if defined EMAIL (
    >>"%STATUS_FILE%" echo signup_email=!EMAIL!
    >>"%STATUS_FILE%" echo signup_run_id=!SIGNUP_RUN_ID!
    >>"%STATUS_FILE%" echo signup_duplicate_retry_used=!SIGNUP_RETRY_USED!
    if defined KODAK_SIGNUP_JSON >>"%STATUS_FILE%" echo kodak_signup_json_path=!KODAK_SIGNUP_JSON!
)

> "%RESULT_FILE%" (
    echo suite,flow,device,status,exit_code,reason,log_file
    echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS_VALUE%,%RUN_EXIT%,%REASON%,"%LOG_FILE%"
)

echo. >> "%LOG_FILE%"
if /I "%AUTOFILL_RESTORE_AFTER_TEST%"=="1" (
    if /I "!ORIG_AUTOFILL_SERVICE!"=="unknown" (
        echo [WARN] Device %DEVICE_ID% - no original autofill_service captured; skip restore>> "%LOG_FILE%"
    ) else (
        echo [INFO] Device %DEVICE_ID% - restoring autofill_service to !ORIG_AUTOFILL_SERVICE!>> "%LOG_FILE%"
        adb -s "%DEVICE_ID%" shell settings put secure autofill_service "!ORIG_AUTOFILL_SERVICE!" >> "%LOG_FILE%" 2>&1
        if errorlevel 1 (
            echo [WARN] Device %DEVICE_ID% - autofill restore failed, continuing>> "%LOG_FILE%"
        ) else (
            echo [INFO] Device %DEVICE_ID% - autofill restore completed>> "%LOG_FILE%"
        )
    )
)

echo. >> "%LOG_FILE%"
echo Final status   : %STATUS_VALUE%>> "%LOG_FILE%"
echo Final reason   : %REASON%>> "%LOG_FILE%"
echo Final exit code: %RUN_EXIT%>> "%LOG_FILE%"
exit /b %RUN_EXIT%
