@echo off
call "%~dp0set_maestro_java.bat"

set SUITE=%1
set FLOW_DIR=%2

echo =====================================
echo RUN SUITE SAME MACHINE
echo =====================================
echo Suite: %SUITE%
echo Flow dir: %FLOW_DIR%

for %%f in ("%FLOW_DIR%\*.yaml") do (
    echo Running %%f
    call "%~dp0run_one_flow_on_device.bat" "%%f" ""
    if errorlevel 1 (
        echo Failure in %%f
        exit /b 1
    )
)

echo =====================================
echo SUITE COMPLETED
echo =====================================
exit /b 0
