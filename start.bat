@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
where python >nul 2>nul
if errorlevel 1 if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python was not found. Install Python 3.11 or newer and try again.
  pause
  exit /b 1
)
set "FRONTEND_READY=0"
if exist "frontend\node_modules\vite\bin\vite.js" set "FRONTEND_READY=1"
if not exist ".env" copy ".env.example" ".env" >nul
start "CampusTwin AI API" cmd /k "cd /d ""%~dp0"" ^&^& ""%PYTHON_EXE%"" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul
if "%FRONTEND_READY%"=="1" (
  start "CampusTwin AI Frontend" cmd /k "cd /d ""%~dp0frontend"" ^&^& npm run dev -- --host 127.0.0.1"
  timeout /t 3 /nobreak >nul
  start "" "http://127.0.0.1:5173"
) else (
  echo [INFO] React/Vite packages are not installed. Opening the dependency-free local demo at /demo.
  echo [INFO] This fallback runs against the same backend; the React production build remains a separate release gate.
  start "" "http://127.0.0.1:8000/demo"
)
endlocal
