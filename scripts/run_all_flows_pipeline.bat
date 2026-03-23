@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."

if not exist reports\raw mkdir reports\raw
if not exist reports\logs mkdir reports\logs
if not exist reports\excel mkdir reports\excel

set "ADB_EXE=adb"
set "PYTHON_EXE=python"

echo =====================================
echo RUNNING FULL PIPELINE (FLOW BY FLOW)
echo =====================================

echo.
echo ===== ADB DEVICES =====
%ADB_EXE% devices

echo.
call scripts\collect_devices.bat
if errorlevel 1 exit /b 1

echo.
echo Connected devices:
for %%D in (%DEVICES%) do echo  - %%D

echo.
echo =====================================
echo RUNNING NON PRINTING FLOWS
echo =====================================
set "FLOWS=flow1.yaml flow2.yaml flow3.yaml flow4.yaml flow5.yaml flow6.yaml flow7.yaml"
for %%F in (%FLOWS%) do (
    echo.
    echo =====================================
    echo Running Non printing flows\%%F on all devices in parallel
    echo =====================================
    call scripts\run_single_flow_parallel.bat "Non printing flows\%%F"
    if errorlevel 1 exit /b 1

    echo Updating Excel for %%F
    %PYTHON_EXE% scripts\update_excel_after_flow.py --flow %%F --type nonprinting
    if errorlevel 1 exit /b 1
)

echo.
echo =====================================
echo RUNNING PRINTING FLOWS
echo =====================================
set "FLOWS=flow1.yaml flow2.yaml flow3.yaml flow4.yaml flow5.yaml flow6.yaml flow7.yaml flow8.yaml flow9.yaml flow10.yaml flow11.yaml"
for %%F in (%FLOWS%) do (
    echo.
    echo =====================================
    echo Running Printing Flow\%%F on all devices in parallel
    echo =====================================
    call scripts\run_single_flow_parallel.bat "Printing Flow\%%F"
    if errorlevel 1 exit /b 1

    echo Updating Excel for %%F
    %PYTHON_EXE% scripts\update_excel_after_flow.py --flow %%F --type printing
    if errorlevel 1 exit /b 1
)

echo.
echo =====================================
echo ALL FLOWS COMPLETED

echo Reports available in:
echo   reports\raw
echo   reports\logs
echo   reports\excel
echo =====================================
exit /b 0
