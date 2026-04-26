@echo off
rem Wrapper for local / CI: same as python scripts\generate_signup_user.py
setlocal
cd /d "%~dp0.."
where python >nul 2>&1 || ( echo python not on PATH & exit /b 1 )
python "%~dp0generate_signup_user.py" %*
exit /b %ERRORLEVEL%
