@echo off
REM Installs Flask into the engine's venv (backend\.venv) and runs the scoring-service tests.
REM Log: ml_service\setup_and_test.log
cd /d "%~dp0"
set PY=..\..\backend\.venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8
echo START %DATE% %TIME% > setup_and_test.log
%PY% -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt -c ..\..\backend\constraints-core.txt >> setup_and_test.log 2>&1
echo PIP_EXIT=%ERRORLEVEL% >> setup_and_test.log
%PY% -m pytest -q -p no:cacheprovider test_app.py >> setup_and_test.log 2>&1
echo TEST_EXIT=%ERRORLEVEL% >> setup_and_test.log
echo Finished. Output is in ml_service\setup_and_test.log
