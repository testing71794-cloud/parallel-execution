@echo off
setlocal EnableExtensions
REM Point Jenkins / local ATP at the parallel-install tree (needs --driver-host-port).
REM Prefer flat bin\; fall back to nested maestro\bin\ (zip layout from install_maestro_parallel.py).
set "MAESTRO_HOME=C:\Tools\maestro-parallel\bin"
if not exist "%MAESTRO_HOME%\maestro.bat" if exist "C:\Tools\maestro-parallel\maestro\bin\maestro.bat" (
  set "MAESTRO_HOME=C:\Tools\maestro-parallel\maestro\bin"
)
set "ATP_MAESTRO_PARALLEL_HOME=%MAESTRO_HOME%"
echo MAESTRO_HOME=%MAESTRO_HOME%
echo ATP_MAESTRO_PARALLEL_HOME=%ATP_MAESTRO_PARALLEL_HOME%
python "%~dp0verify_maestro_parallel_cli.py"
exit /b %ERRORLEVEL%
