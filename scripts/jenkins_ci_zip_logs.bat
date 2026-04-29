@echo off
setlocal EnableExtensions
cd /d "%~1"
python -c "import sys; from pathlib import Path; r=Path('.'); sys.path.insert(0, str(r.resolve())); from mailout.send_email import build_execution_logs_zip; z=build_execution_logs_zip(r); print('execution_logs.zip =>', z)"
