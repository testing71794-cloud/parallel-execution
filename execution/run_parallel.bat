@echo off
setlocal
cd /d "%~dp0.."
python execution\run_parallel_devices.py %*
exit /b %ERRORLEVEL%
