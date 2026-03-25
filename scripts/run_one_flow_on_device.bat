@echo off
REM =====================================
REM RUN ONE FLOW ON ONE DEVICE (FIXED)
REM =====================================

set DEVICE_ID=%1
set FLOW_FILE=%2
set FLOW_NAME=%3

echo Running %FLOW_NAME% on device %DEVICE_ID%

REM Ensure logs folder exists
if not exist logs mkdir logs

REM FIX: Proper use of start with cmd /c and redirection inside quotes
start "" cmd /c "maestro test \"%FLOW_FILE%\" --device %DEVICE_ID% > logs\%DEVICE_ID%_%FLOW_NAME%.log 2>&1"
