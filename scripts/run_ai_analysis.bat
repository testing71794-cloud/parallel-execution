@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist package.json (
    echo No package.json at repo root — skipping AI doctor.
    exit /b 0
)

where npm >nul 2>&1 || (
    echo npm not on PATH — skipping AI doctor.
    exit /b 0
)

echo Running npm run doctor ^(requires Node; on Windows Git Bash helps if doctor.sh is used^)...
call npm run doctor
exit /b %ERRORLEVEL%
