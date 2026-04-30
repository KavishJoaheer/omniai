@echo off
REM ── Omni-AI Demo Launcher ────────────────────────────────────────────────────
REM Starts backend + frontend in two windows and opens the browser.
REM Run from the repo root:  start-demo.bat

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║          Omni-AI  —  Demo Launcher               ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Starting backend  (port 9380) ...
start "Omni-AI Backend" cmd /k "cd /d %~dp0backend && uvicorn main:app --host 0.0.0.0 --port 9380 --reload"

echo  Waiting 4 seconds for backend to boot ...
timeout /t 4 /nobreak >nul

echo  Starting frontend (port 5173) ...
start "Omni-AI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo  Waiting 3 seconds for frontend to compile ...
timeout /t 3 /nobreak >nul

echo.
echo  ──────────────────────────────────────────────────
echo   Frontend :  http://localhost:5173
echo   API docs :  http://localhost:9380/docs
echo   Email    :  admin@omniai.local
echo   Password :  Admin12345!
echo  ──────────────────────────────────────────────────
echo.
echo  (Optional) seed demo data in a third terminal:
echo     cd backend
echo     python demo_seed.py
echo.
start http://localhost:5173
