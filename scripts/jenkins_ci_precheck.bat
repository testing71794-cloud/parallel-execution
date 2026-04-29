@echo off
setlocal EnableExtensions
cd /d "%~1"
where java
java -version
call scripts/precheck_environment.bat "%~2" "%~3" || (echo 1> precheck_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
