@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
if not exist "automation_with_testcases\config.yaml" ( echo config.yaml missing & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_automation_with_testcases.ps1" -RepoRoot "%CD%"
set "E=%ERRORLEVEL%"
exit /b %E%
