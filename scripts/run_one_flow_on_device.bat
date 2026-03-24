@echo off
setlocal EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_NAME=%~2"
set "FLOW_PATH=%~3"
set "DEVICE_ID=%~4"
set "MAESTRO_OVERRIDE=%~5"
set "APP_PACKAGE=%~6"
set "RETRY_FAILED=%~7"

set "PROJECT_DIR=%CD%"
set "REPORT_DIR=%PROJECT_DIR%\reports\%SUITE_NAME%\%FLOW_NAME%\%DEVICE_ID%"
set "LOG_DIR=%REPORT_DIR%\logs"
set "SCREENSHOT_DIR=%PROJECT_DIR%\.maestro\screenshots\%DEVICE_ID%\%SUITE_NAME%\%FLOW_NAME%"
set "STATUS_DIR=%PROJECT_DIR%\status"
set "FLOW_LOG=%LOG_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.log"
set "KICKOFF_LOG=%LOG_DIR%\kickoff_%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.log"
set "STATUS_PASS=%STATUS_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.pass"
set "STATUS_FAIL=%STATUS_DIR%\%SUITE_NAME%_%FLOW_NAME%_%DEVICE_ID%.fail"

if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%SCREENSHOT_DIR%" mkdir "%SCREENSHOT_DIR%"
if not exist "%STATUS_DIR%" mkdir "%STATUS_DIR%"

del /q "%STATUS_PASS%" >nul 2>&1
del /q "%STATUS_FAIL%" >nul 2>&1

set "MAESTRO_CMD=maestro"
if not "%MAESTRO_OVERRIDE%"=="" (
    set "MAESTRO_CMD=%MAESTRO_OVERRIDE%"
) else if exist "C:\maestro\bin\maestro.exe" (
    set "MAESTRO_CMD=C:\maestro\bin\maestro.exe"
)

echo ===================================== > "%KICKOFF_LOG%"
echo RUN ONE FLOW ON ONE DEVICE >> "%KICKOFF_LOG%"
echo ===================================== >> "%KICKOFF_LOG%"
echo Suite: %SUITE_NAME% >> "%KICKOFF_LOG%"
echo Flow: %FLOW_NAME% >> "%KICKOFF_LOG%"
echo Flow path: %FLOW_PATH% >> "%KICKOFF_LOG%"
echo Device: %DEVICE_ID% >> "%KICKOFF_LOG%"
echo Maestro: %MAESTRO_CMD% >> "%KICKOFF_LOG%"
echo Retry failed once: %RETRY_FAILED% >> "%KICKOFF_LOG%"
echo Started: %date% %time% >> "%KICKOFF_LOG%"

adb -s "%DEVICE_ID%" get-state >nul 2>&1
if errorlevel 1 (
    echo Device %DEVICE_ID% is not available. > "%FLOW_LOG%"
    echo FAILED: device not available. >> "%KICKOFF_LOG%"
    echo device unavailable> "%STATUS_FAIL%"
    exit /b 1
)

echo Starting %FLOW_NAME% on %DEVICE_ID%
call "%MAESTRO_CMD%" test "%FLOW_PATH%" --device "%DEVICE_ID%" > "%FLOW_LOG%" 2>&1
set "RUN_EXIT=%ERRORLEVEL%"

if "%RUN_EXIT%"=="0" (
    echo pass> "%STATUS_PASS%"
    echo Finished: %date% %time% >> "%KICKOFF_LOG%"
    echo Exit code: %RUN_EXIT% >> "%KICKOFF_LOG%"
    echo PASSED on device %DEVICE_ID%
    exit /b 0
)

echo First attempt failed with exit %RUN_EXIT% >> "%KICKOFF_LOG%"

if /i "%RETRY_FAILED%"=="true" (
    echo Retrying once for %FLOW_NAME% on %DEVICE_ID% >> "%KICKOFF_LOG%"
    call "%MAESTRO_CMD%" test "%FLOW_PATH%" --device "%DEVICE_ID%" >> "%FLOW_LOG%" 2>&1
    set "RUN_EXIT=%ERRORLEVEL%"
)

echo Finished: %date% %time% >> "%KICKOFF_LOG%"
echo Exit code: %RUN_EXIT% >> "%KICKOFF_LOG%"

if not "%RUN_EXIT%"=="0" (
    echo fail> "%STATUS_FAIL%"
    echo FAILED on device %DEVICE_ID% (exit %RUN_EXIT%)
    exit /b 1
)

echo pass> "%STATUS_PASS%"
echo PASSED on device %DEVICE_ID%
exit /b 0
