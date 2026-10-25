@echo off
REM Installs core Vyakhya deps into backend\.venv and writes a log you can read.
cd /d "%~dp0"
echo START %DATE% %TIME% > setup_env.log
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --progress-bar off --retries 5 --timeout 60 -r requirements-core.txt >> setup_env.log 2>&1
echo PIP_EXIT=%ERRORLEVEL% >> setup_env.log
.venv\Scripts\python.exe -c "import fastapi, pydantic, sklearn, xgboost, pandas, numpy; print('IMPORT_OK fastapi', fastapi.__version__, 'pydantic', pydantic.VERSION, 'sklearn', sklearn.__version__, 'xgboost', xgboost.__version__, 'pandas', pandas.__version__)" >> setup_env.log 2>&1
echo DONE %DATE% %TIME% >> setup_env.log
