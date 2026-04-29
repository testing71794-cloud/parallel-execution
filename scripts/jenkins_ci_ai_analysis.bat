@echo off
setlocal EnableExtensions
cd /d "%~1"
if not exist build-summary mkdir build-summary
if not exist build-summary\ai_status.txt echo AI_STATUS=FILE_MISSING > build-summary\ai_status.txt
call scripts/run_ai_analysis.bat || (echo 1> ai_failed.flag)
