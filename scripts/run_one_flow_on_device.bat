@echo off
call "%~dp0set_maestro_java.bat"
set FLOW=%1
set DEVICE=%2

echo Running %FLOW% on %DEVICE%
maestro --verbose test "%FLOW%" --device "%DEVICE%"
