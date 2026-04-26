@echo off
rem flow1b.yaml only: set FULL_NAME, PASSWORD, EMAIL (kodak_<ts>_<random>@test.com).
rem Do not setlocal: caller must see variables.
set "FULL_NAME=Nitesh"
set "PASSWORD=252546Nm#"
set "EMAIL="
for /f "delims=" %%A in ('python "%~dp0flow1b_signup_email.py"') do set "EMAIL=%%A"
if not defined EMAIL exit /b 1
if "%EMAIL%"=="" exit /b 1
exit /b 0
