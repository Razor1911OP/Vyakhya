@echo off
REM ONE COMMAND: rule tests -> train + evaluate + export frozen registry -> engine tests -> /score smoke test.
REM Logs: backend\logs\test_rules.log, train_eval.log, test_engine_feedback.log, smoke_score_api.log
cd /d "%~dp0"
call run.bat tests\test_rules.py
call run.bat train_eval.py
call run.bat tests\test_engine_feedback.py
call run.bat smoke_score_api.py
echo All steps finished. Read backend\logs\*.log and metrics\risk_eval.md
