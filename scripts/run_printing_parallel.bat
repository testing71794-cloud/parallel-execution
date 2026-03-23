@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."
if not exist reports\raw mkdir reports\raw
if not exist reports\logs mkdir reports\logs
if not exist reports\excel mkdir reports\excel

call scripts\collect_devices.bat
if errorlevel 1 exit /b 1

set "FLOWS=flow1.yaml flow2.yaml flow3.yaml flow4.yaml flow5.yaml flow6.yaml flow7.yaml flow8.yaml flow9.yaml flow10.yaml flow11.yaml"
for %%F in (%FLOWS%) do (
    echo.
    echo =====================================
    echo Running Printing Flow\%%F on all devices in parallel
    echo =====================================
    call scripts\run_single_flow_parallel.bat "Printing Flow\%%F"
    if errorlevel 1 exit /b 1

    echo Updating Excel for %%F
    python scripts\update_excel_after_flow.py --flow %%F --type printing
    if errorlevel 1 exit /b 1
)
exit /b 0
