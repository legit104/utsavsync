@echo off
rem Start the UtsavSync backend. Double-click this file or run start.bat.
rem First run: creates .venv and installs packages. Later runs: starts straight away.
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Setting up Python environment for the first time...
    python -m venv .venv || (echo Python not found. Install Python 3.11+ from python.org and tick "Add to PATH". & pause & exit /b 1)
)

rem Reinstall packages only when requirements.txt changed since the last install.
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>&1
if errorlevel 1 (
    echo Installing packages...
    .venv\Scripts\python -m pip install -q -r requirements.txt || (echo Package install failed. & pause & exit /b 1)
    copy /y requirements.txt .venv\installed-requirements.txt >nul
)

echo.
echo Backend starting at http://localhost:8000  (API docs: http://localhost:8000/docs)
echo Press Ctrl+C to stop.
echo.
.venv\Scripts\python -m uvicorn app.main:app --reload
pause
