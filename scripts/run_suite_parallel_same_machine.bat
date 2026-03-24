@echo off
setlocal EnableDelayedExpansion

set "SUITE_NAME=%~1"
set "FLOW_DIR=%~2"
set "DEVICE1_ID=%~3"
set "DEVICE2_ID=%~4"
set "MAESTRO_OVERRIDE=%~5"
set "APP_PACKAGE=%~6"
set "RETRY_FAILED=%~7"

set "PROJECT_DIR=%CD%"
set "COLLECT_DIR=%PROJECT_DIR%\collected-artifacts"
set "PIPELINE_FAIL_FLAG=%PROJECT_DIR%\pipeline_failed.flag"
set "RUNNER_DIR=%PROJECT_DIR%\temp-runners"

if not exist "%COLLECT_DIR%" mkdir "%COLLECT_DIR%"
if not exist "%RUNNER_DIR%" mkdir "%RUNNER_DIR%"

for %%F in ("%FLOW_DIR%\*.yaml") do (
    set "FLOW_PATH=%%F"
    set "FLOW_NAME=%%~nF"

    echo =====================================
    echo Running !FLOW_NAME! on both devices in parallel
    echo Pipeline will continue even if one device fails
    echo =====================================

    set "R1=%RUNNER_DIR%\run_!SUITE_NAME!_!FLOW_NAME!_%DEVICE1_ID%.cmd"
    set "R2=%RUNNER_DIR%\run_!SUITE_NAME!_!FLOW_NAME!_%DEVICE2_ID%.cmd"
    set "DONE1=%RUNNER_DIR%\done_!SUITE_NAME!_!FLOW_NAME!_%DEVICE1_ID%.flag"
    set "DONE2=%RUNNER_DIR%\done_!SUITE_NAME!_!FLOW_NAME!_%DEVICE2_ID%.flag"

    del /q "!DONE1!" >nul 2>&1
    del /q "!DONE2!" >nul 2>&1

    > "!R1!" echo @echo off
    >> "!R1!" echo cd /d "%PROJECT_DIR%"
    >> "!R1!" echo call scripts\run_one_flow_on_device.bat "%SUITE_NAME%" "!FLOW_NAME!" "!FLOW_PATH!" "%DEVICE1_ID%" "%MAESTRO_OVERRIDE%" "%APP_PACKAGE%" "%RETRY_FAILED%"
    >> "!R1!" echo if errorlevel 1 echo 1^> "%PROJECT_DIR%\%SUITE_NAME%_!FLOW_NAME!_%DEVICE1_ID%.failed"
    >> "!R1!" echo echo done^> "!DONE1!"

    > "!R2!" echo @echo off
    >> "!R2!" echo cd /d "%PROJECT_DIR%"
    >> "!R2!" echo call scripts\run_one_flow_on_device.bat "%SUITE_NAME%" "!FLOW_NAME!" "!FLOW_PATH!" "%DEVICE2_ID%" "%MAESTRO_OVERRIDE%" "%APP_PACKAGE%" "%RETRY_FAILED%"
    >> "!R2!" echo if errorlevel 1 echo 1^> "%PROJECT_DIR%\%SUITE_NAME%_!FLOW_NAME!_%DEVICE2_ID%.failed"
    >> "!R2!" echo echo done^> "!DONE2!"

    start "FLOW1" cmd /c "!R1!"
    start "FLOW2" cmd /c "!R2!"

    call :wait_for_flags "!DONE1!" "!DONE2!"

    if exist "%PROJECT_DIR%\%SUITE_NAME%_!FLOW_NAME!_%DEVICE1_ID%.failed" (
        echo 1> "%PIPELINE_FAIL_FLAG%"
    )
    if exist "%PROJECT_DIR%\%SUITE_NAME%_!FLOW_NAME!_%DEVICE2_ID%.failed" (
        echo 1> "%PIPELINE_FAIL_FLAG%"
    )
)

if exist reports xcopy /E /I /Y reports "%COLLECT_DIR%\reports" >nul
if exist .maestro\screenshots xcopy /E /I /Y .maestro\screenshots "%COLLECT_DIR%\.maestro\screenshots" >nul
if exist status xcopy /E /I /Y status "%COLLECT_DIR%\status" >nul

if exist "%PIPELINE_FAIL_FLAG%" (
    exit /b 1
)
exit /b 0

:wait_for_flags
set "FLAG1=%~1"
set "FLAG2=%~2"
:loop
if exist "%FLAG1%" if exist "%FLAG2%" exit /b 0
timeout /t 3 /nobreak >nul
goto loop
