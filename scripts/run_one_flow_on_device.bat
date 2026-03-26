@echo off
setlocal

set "FLOW_PATH=%~1"
set "FLOW_NAME=%~2"
set "DEVICE_ID=%~3"

echo Running %FLOW_NAME% on %DEVICE_ID%

maestro test "%FLOW_PATH%" --device "%DEVICE_ID%"

exit /b %ERRORLEVEL%
