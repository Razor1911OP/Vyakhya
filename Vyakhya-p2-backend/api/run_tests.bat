@echo off
REM Runs the API test suite (in-memory MongoDB, no Atlas) and writes everything to jest_run.log
cd /d "%~dp0"
set "PATH=C:\Program Files\nodejs;%PATH%"
echo START %DATE% %TIME% > jest_run.log
call npm test -- --ci >> jest_run.log 2>&1
echo EXIT=%ERRORLEVEL% >> jest_run.log
echo Finished. Output is in api\jest_run.log
