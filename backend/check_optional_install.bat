@echo off
REM DRY RUN ONLY: shows what installing the optional MiniLM comparison would do. Installs nothing.
REM Core pins are passed as constraints, so a conflict with numpy/scikit-learn/pandas fails here
REM instead of silently changing the core environment.
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\optional_dryrun.log
echo START %DATE% %TIME% > %LOG%
.venv\Scripts\python.exe -m pip install --dry-run --disable-pip-version-check --progress-bar off -r requirements-optional.txt -c constraints-core.txt --report logs\optional_dryrun_report.json >> %LOG% 2>&1
echo EXIT=%ERRORLEVEL% >> %LOG%
echo Finished. Output is in backend\%LOG%
