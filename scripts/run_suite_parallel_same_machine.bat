@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE=%~1"
set "FLOW_DIR=%~2"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"

if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"

for /f "tokens=1" %%d in ('adb devices ^| findstr /R "device$"') do (
    echo Running on %%d
    call scripts\run_one_flow_on_device.bat %SUITE% "%FLOW_DIR%\flow1.yaml" %%d "%APP_ID%" "%CLEAR_STATE%" "%MAESTRO_CMD%"
)
