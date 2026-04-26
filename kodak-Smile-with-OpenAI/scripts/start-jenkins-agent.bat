@echo off
REM Jenkins agent launcher for Windows (devices PC)
REM 1. Create C:\JenkinsAgent folder
REM 2. Paste the java -jar ... command from Jenkins Nodes page here
REM 3. Add your secret and Jenkins URL
REM 4. Run this script (or double-click)

set AGENT_DIR=C:\JenkinsAgent
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
cd /d "%AGENT_DIR%"

REM === REPLACE THIS with the command from Jenkins ===
REM Go to: Jenkins -> Manage Jenkins -> Nodes -> your agent -> Run from agent command line
REM Copy the "java -jar agent.jar ..." line and paste below (remove the REM)
REM Example:
REM java -jar agent.jar -url http://34.171.234.138:8080/ -secret YOUR_SECRET -name my-pc-devices -workDir "%AGENT_DIR%"

echo.
echo Paste your agent command from Jenkins into this script, then run again.
echo Or run the command manually from Jenkins agent page.
echo.
pause
