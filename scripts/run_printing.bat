@echo off
cd /d "%~dp0.."

echo Running Printing Flow (single device - first available^)...
adb devices
REM Official CLI: https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options
maestro test "Printing Flow"

pause
