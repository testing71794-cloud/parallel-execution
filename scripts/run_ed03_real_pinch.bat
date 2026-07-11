@echo off

setlocal EnableExtensions

REM ED_03 with REAL two-finger pinch (Appium W3C multitouch).

REM Usage: scripts\run_ed03_real_pinch.bat [DEVICE_SERIAL]

REM Flow: ED_03a (Maestro) -> Appium W3C pinch -> ED_03c double-tap -> ED_03b pan/exit -> AI verify



set "REPO_ROOT=%~dp0.."

cd /d "%REPO_ROOT%"

call "%REPO_ROOT%\automation\appium-gestures\scripts\run_ed03_verify.bat" %*

exit /b %ERRORLEVEL%

