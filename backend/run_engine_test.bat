@echo off
REM Runs the detection engine test and writes all output to test_engine.log
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo START %DATE% %TIME% > test_engine.log
.venv\Scripts\python.exe test_engine.py >> test_engine.log 2>&1
echo TEST_EXIT=%ERRORLEVEL% >> test_engine.log
echo DONE %DATE% %TIME% >> test_engine.log
echo Finished. Output is in backend\test_engine.log
