@echo off
setlocal

set DEVICE=%~1
set FLOW=%~2
set SUITE=%~3
set FLOWNAME=%~4

if not exist reports\raw mkdir reports\raw
if not exist reports\logs mkdir reports\logs
if not exist reports\state mkdir reports\state

echo Running %FLOWNAME% on %DEVICE% > "reports\logs\%FLOWNAME%_%DEVICE%.log"

maestro test "%FLOW%" -d %DEVICE% --format junit --output "reports\raw\%FLOWNAME%_%DEVICE%.xml" >> "reports\logs\%FLOWNAME%_%DEVICE%.log" 2>&1

echo %errorlevel% > "reports\state\%FLOWNAME%_%DEVICE%.exit"
type nul > "reports\state\%FLOWNAME%_%DEVICE%.done"

exit /b 0
