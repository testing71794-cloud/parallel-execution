@echo off
setlocal EnableExtensions
cd /d "%~1"
call scripts/list_devices.bat || (echo 1> device_detection_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
