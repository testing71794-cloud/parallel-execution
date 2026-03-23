@echo off
setlocal
cd /d %~dp0..

echo =====================================
echo RUNNING PRINTING FLOWS (FLOW BY FLOW, ALL DEVICES, EXCEL UPDATE AFTER EACH FLOW)
echo =====================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_flows_printing.ps1"
exit /b %errorlevel%
