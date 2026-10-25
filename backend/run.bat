@echo off
REM Reusable runner: executes a Python script in backend\.venv and logs everything.
REM Usage (from the backend folder):   .\run.bat jobs\gen_synthetic.py
REM Output goes to backend\logs\<script_name>.log
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set LOG=logs\%~n1.log
echo START %DATE% %TIME% > "%LOG%"
.venv\Scripts\python.exe %* >> "%LOG%" 2>&1
echo EXIT=%ERRORLEVEL% >> "%LOG%"
echo Finished. Output is in backend\%LOG%
