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

if "%SUITE%"=="" exit /b 10
if "%FLOW_PATH%"=="" exit /b 11
if "%DEVICE_ID%"=="" exit /b 12
if "%APP_ID%"=="" exit /b 13

REM Force exact Java and Maestro paths
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
set "MAESTRO_BIN=C:\maestro\bin\maestro.bat"

if not exist "%JAVA_HOME%\bin\java.exe" exit /b 14
if not exist "%MAESTRO_BIN%" exit /b 15

REM Clean Java environment that can break launcher behavior
set "CLASSPATH="
set "JAVA_TOOL_OPTIONS="
set "_JAVA_OPTIONS="
set "JDK_JAVA_OPTIONS="

REM Put exact Java and Maestro first in PATH
set "PATH=%JAVA_HOME%\bin;C:\maestro\bin;%PATH%"

REM Resolve repo root
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

REM Extract flow name
for %%I in ("%FLOW_PATH%") do set "FLOW_NAME=%%~nI"

REM Directories
set "LOG_DIR=%REPO_ROOT%\reports\%SUITE%\logs"
set "RESULT_DIR=%REPO_ROOT%\reports\%SUITE%\results"
set "STATUS_DIR=%REPO_ROOT%\status"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

set "LOG_FILE=%LOG_DIR%\%FLOW_NAME%_%DEVICE_ID%.log"
set "RESULT_FILE=%RESULT_DIR%\%FLOW_NAME%_%DEVICE_ID%.csv"
set "STATUS_FILE=%STATUS_DIR%\%SUITE%__%FLOW_NAME%__%DEVICE_ID%.txt"

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
echo JAVA_HOME        : %JAVA_HOME%
echo MAESTRO_BIN      : %MAESTRO_BIN%
echo CLASSPATH        : [%CLASSPATH%]
echo JAVA_TOOL_OPTIONS: [%JAVA_TOOL_OPTIONS%]
echo _JAVA_OPTIONS    : [%_JAVA_OPTIONS%]
echo JDK_JAVA_OPTIONS : [%JDK_JAVA_OPTIONS%]
echo =====================================
) > "%LOG_FILE%"

where java >> "%LOG_FILE%" 2>&1
java -version >> "%LOG_FILE%" 2>&1
where maestro >> "%LOG_FILE%" 2>&1
where maestro.bat >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

if not exist "%FLOW_PATH%" (
    echo ERROR: Flow file not found: %FLOW_PATH%>> "%LOG_FILE%"
    set "RUN_EXIT=20"
    goto :write_result
)

where adb >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: adb not found in PATH>> "%LOG_FILE%"
    set "RUN_EXIT=21"
    goto :write_result
)

adb -s "%DEVICE_ID%" get-state >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Device not ready: %DEVICE_ID%>> "%LOG_FILE%"
    set "RUN_EXIT=22"
    goto :write_result
)

if /I "%CLEAR_STATE%"=="true" (
    echo Clearing app state...>> "%LOG_FILE%"
    adb -s "%DEVICE_ID%" shell pm clear "%APP_ID%" >> "%LOG_FILE%" 2>&1
    echo Clear-state exit code: !errorlevel!>> "%LOG_FILE%"
)

echo Starting Maestro test...>> "%LOG_FILE%"
echo Command: call "%MAESTRO_BIN%" test "%FLOW_PATH%" --device "%DEVICE_ID%">> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

call "%MAESTRO_BIN%" test "%FLOW_PATH%" --device "%DEVICE_ID%" >> "%LOG_FILE%" 2>&1
set "RUN_EXIT=%ERRORLEVEL%"

:write_result
if "%RUN_EXIT%"=="0" (
    set "STATUS_VALUE=PASS"
    set "REASON=OK"
) else (
    set "STATUS_VALUE=FAIL"
    set "REASON=MAESTRO_FAILED"
)

> "%STATUS_FILE%" (
    echo suite=%SUITE%
    echo flow=%FLOW_NAME%
    echo device=%DEVICE_ID%
    echo status=%STATUS_VALUE%
    echo exit_code=%RUN_EXIT%
    echo reason=%REASON%
)

> "%RESULT_FILE%" (
    echo suite,flow,device,status,exit_code,reason,log_file
    echo %SUITE%,%FLOW_NAME%,%DEVICE_ID%,%STATUS_VALUE%,%RUN_EXIT%,%REASON%,"%LOG_FILE%"
)

echo. >> "%LOG_FILE%"
echo Final exit code: %RUN_EXIT%>> "%LOG_FILE%"
exit /b %RUN_EXIT%