@echo off
setlocal EnableExtensions
REM GA_06 pinch zoom in — real Appium W3C multitouch.
REM Usage: scripts\run_ga06_real_pinch.bat [DEVICE_SERIAL]
set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"
call "%REPO_ROOT%\automation\appium-gestures\scripts\run_ga_pinch_verify.bat" pinch-out %*
exit /b %ERRORLEVEL%
