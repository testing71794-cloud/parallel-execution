@echo off
setlocal EnableExtensions
REM GA_05 pinch zoom out — real Appium W3C multitouch.
REM Usage: scripts\run_ga05_real_pinch.bat [DEVICE_SERIAL]
set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"
call "%REPO_ROOT%\automation\appium-gestures\scripts\run_ga_pinch_verify.bat" pinch-in %*
exit /b %ERRORLEVEL%
