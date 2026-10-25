@echo off
REM Starts the full Vyakhya prototype in three windows: scoring service (:8000), API (:3000), frontend (:5173).
REM Needs: backend\.venv (Python engine env), Node 20.6+, Vyakhya-p2-backend\api\.env with MONGO_URL.
set ROOT=%~dp0
set "PATH=C:\Program Files\nodejs;%PATH%"
start "Vyakhya scoring :8000" cmd /k "cd /d "%ROOT%Vyakhya-p2-backend\ml_service" && "%ROOT%backend\.venv\Scripts\python.exe" app.py"
start "Vyakhya API :3000" cmd /k "cd /d "%ROOT%Vyakhya-p2-backend\api" && node --env-file=.env server.js"
start "Vyakhya frontend :5173" cmd /k "cd /d "%ROOT%frontend" && npx vite --port 5173"
echo Started. Open http://localhost:5173 and sign in as analyst / analyst123 (or user / user123).
