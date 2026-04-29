@echo off
setlocal EnableExtensions
cd /d "%~1"
echo === SAFE DISK CLEANUP POST ===
call scripts\safe_disk_cleanup.bat POST "%CD%"
echo === DISK USAGE REPORT ===
call scripts\safe_disk_cleanup.bat REPORT "%CD%"
