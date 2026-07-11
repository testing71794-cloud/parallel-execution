@echo off
setlocal EnableExtensions
REM Start OpenRouter verify server (port 8765) in background for GA_02 / gallery Jenkins runs.
cd /d "%~dp0.."
where py >nul 2>&1 && set "PY=py -3" || set "PY=python"
%PY% "%~dp0ensure_maestro_verify_server.py"
exit /b %ERRORLEVEL%
