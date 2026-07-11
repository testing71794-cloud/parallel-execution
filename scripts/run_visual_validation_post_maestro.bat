@echo off
setlocal EnableExtensions
REM Opt-in post-Maestro AI visual validation (never changes Maestro exit code).
REM Usage:
REM   scripts\run_visual_validation_post_maestro.bat --status-file status\suite__flow__device.txt

set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"
py -3 "%REPO_ROOT%\scripts\run_visual_validation_post_maestro.py" %*
exit /b 0
