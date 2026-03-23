@echo off
cd /d "%~dp0.."

echo Running Non Printing Flows (suite folder - uses config.yaml if needed^)...
adb devices
REM https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options
maestro test "Non printing flows"

pause
