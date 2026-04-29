@echo off
setlocal EnableExtensions
cd /d "%~1"
if not exist build-summary mkdir build-summary
python scripts/test_ai_connection.py
if exist build-summary\ai_status.txt (type build-summary\ai_status.txt) else (echo No ai_status.txt)
