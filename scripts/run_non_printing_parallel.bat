@echo off
setlocal
cd /d %~dp0..

echo =====================================
echo RUNNING NON PRINTING FLOWS (PARALLEL PER FLOW ACROSS DEVICES)
echo =====================================

powershell -ExecutionPolicy Bypass -File "%~dp0run_flows_non_printing.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo Non-printing flows completed with failures.
    exit /b 1
)

echo Non-printing flows completed successfully.
exit /b 0
