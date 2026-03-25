@echo off
setlocal EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_DIR=%~2"
set "MAESTRO_OVERRIDE=%~3"
set "APP_PACKAGE=%~4"
set "RETRY_FAILED=%~5"

set "PROJECT_DIR=%CD%"
set "COLLECT_DIR=%PROJECT_DIR%\collected-artifacts"
set "PIPELINE_FAIL_FLAG=%PROJECT_DIR%\pipeline_failed.flag"
set "RUNNER_DIR=%PROJECT_DIR%\temp-runners"

if not exist "%COLLECT_DIR%" mkdir "%COLLECT_DIR%"
if not exist "%RUNNER_DIR%" mkdir "%RUNNER_DIR%"

del /q "%PROJECT_DIR%\*.failed" >nul 2>&1
del /q "%RUNNER_DIR%\done_*.flag" >nul 2>&1
del /q "%RUNNER_DIR%\run_*.cmd" >nul 2>&1

set /a DEVICE_COUNT=0
for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if /I "%%B"=="device" (
        set /a DEVICE_COUNT+=1
        set "DEVICE_!DEVICE_COUNT!=%%A"
    )
)

if !DEVICE_COUNT! EQU 0 (
    echo ERROR: No Android devices connected.
    echo 1> "%PIPELINE_FAIL_FLAG%"
    exit /b 1
)

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo Suite: %SUITE_NAME%
echo Flow dir: %FLOW_DIR%
echo Devices found: !DEVICE_COUNT!
echo Retry failed once: %RETRY_FAILED%
echo.

for %%F in ("%FLOW_DIR%\*.yaml") do (
    set "FLOW_PATH=%%F"
    set "FLOW_NAME=%%~nF"

    echo =====================================
    echo Running !FLOW_NAME! on all devices in parallel
    echo =====================================

    for /L %%I in (1,1,!DEVICE_COUNT!) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        set "SAFE_DEVICE_ID=!DEVICE_ID::=_%!"
        set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:/=_%!"
        set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:\=_%!"
        set "RUN_CMD=%RUNNER_DIR%\run_%SUITE_NAME%_!FLOW_NAME!_!SAFE_DEVICE_ID!.cmd"
        set "DONE_FLAG=%RUNNER_DIR%\done_%SUITE_NAME%_!FLOW_NAME!_!SAFE_DEVICE_ID!.flag"
        set "FAIL_FLAG=%PROJECT_DIR%\%SUITE_NAME%__!FLOW_NAME!__!SAFE_DEVICE_ID!.failed"

        del /q "!DONE_FLAG!" >nul 2>&1
        del /q "!FAIL_FLAG!" >nul 2>&1

        > "!RUN_CMD!" echo @echo off
        >> "!RUN_CMD!" echo cd /d "%PROJECT_DIR%"
        >> "!RUN_CMD!" echo call scripts\run_one_flow_on_device.bat "%SUITE_NAME%" "!FLOW_NAME!" "!FLOW_PATH!" "!DEVICE_ID!" "%MAESTRO_OVERRIDE%" "%APP_PACKAGE%" "%RETRY_FAILED%"
        >> "!RUN_CMD!" echo if errorlevel 1 echo 1^> "!FAIL_FLAG!"
        >> "!RUN_CMD!" echo echo done^> "!DONE_FLAG!"

        start "RUN_!FLOW_NAME!_%%I" cmd /c "!RUN_CMD!"
    )

    call :wait_for_all !DEVICE_COUNT! "%SUITE_NAME%" "!FLOW_NAME!" 1800
    if errorlevel 1 (
        echo Timeout waiting for !FLOW_NAME! completion flags.
        echo 1> "%PIPELINE_FAIL_FLAG%"
    )

    for /L %%I in (1,1,!DEVICE_COUNT!) do (
        call set "DEVICE_ID=%%DEVICE_%%I%%"
        set "SAFE_DEVICE_ID=!DEVICE_ID::=_%!"
        set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:/=_%!"
        set "SAFE_DEVICE_ID=!SAFE_DEVICE_ID:\=_%!"
        if exist "%PROJECT_DIR%\%SUITE_NAME%__!FLOW_NAME!__!SAFE_DEVICE_ID!.failed" (
            echo 1> "%PIPELINE_FAIL_FLAG%"
        )
    )
)

if exist reports xcopy /E /I /Y reports "%COLLECT_DIR%\reports" >nul
if exist .maestro\screenshots xcopy /E /I /Y .maestro\screenshots "%COLLECT_DIR%\.maestro\screenshots" >nul
if exist status xcopy /E /I /Y status "%COLLECT_DIR%\status" >nul

if exist "%PIPELINE_FAIL_FLAG%" exit /b 1
exit /b 0

:wait_for_all
setlocal EnableDelayedExpansion
set /a TARGET_COUNT=%~1
set "WAIT_SUITE=%~2"
set "WAIT_FLOW=%~3"
set /a MAX_WAIT=%~4
set /a ELAPSED=0
:wait_loop
set /a DONE_COUNT=0
for %%G in ("%RUNNER_DIR%\done_%WAIT_SUITE%_%WAIT_FLOW%_*.flag") do (
    if exist "%%~fG" set /a DONE_COUNT+=1
)
if !DONE_COUNT! GEQ !TARGET_COUNT! (
    endlocal & exit /b 0
)
if !ELAPSED! GEQ !MAX_WAIT! (
    endlocal & exit /b 1
)
timeout /t 5 /nobreak >nul
set /a ELAPSED+=5
goto wait_loop
