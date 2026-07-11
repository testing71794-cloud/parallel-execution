@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>&1 && set "PY=py -3" || set "PY=python"
echo Starting Maestro OpenRouter verify server on http://127.0.0.1:8765
echo - Uses saved GA_02 screenshot when found under reports/gallery/maestro-debug
echo - Falls back to adb screencap when Maestro Studio does not write PNG to disk
echo Leave this window open while running GA_02 in Maestro Studio.
echo Or run: powershell -File scripts/start_ga02_studio_verify.ps1
%PY% "%~dp0maestro_openrouter_verify_server.py"
