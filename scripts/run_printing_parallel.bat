\
@echo off
setlocal

cd /d %~dp0..

echo =====================================
echo RUNNING PRINTING FLOWS (SEQUENTIAL BY FLOW)
echo =====================================

powershell -ExecutionPolicy Bypass -File "%~dp0run_flows_printing.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo Printing flows completed with failures.
    exit /b 1
)

echo Printing flows completed successfully.
exit /b 0
