@echo off
echo =====================================
echo RUNNING NON PRINTING FLOWS (PARALLEL PER FLOW ACROSS DEVICES)
echo =====================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_flows_non_printing.ps1"
exit /b %errorlevel%