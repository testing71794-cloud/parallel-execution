@echo off
call "%~dp0set_maestro_java.bat"

set FLOW=%1
set DEVICE=%2

echo =====================================
echo RUN ONE FLOW ON DEVICE
echo =====================================
echo Flow: %FLOW%
echo Device: %DEVICE%

maestro --verbose test "%FLOW%" --device "%DEVICE%"
exit /b %ERRORLEVEL%
