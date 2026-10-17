@echo off
rem Start the UtsavSync backend. Double-click this file or run start.bat.
rem Add "lan" (or use start-lan.bat) so other laptops on the same trusted Wi-Fi can reach it.
rem First run: creates .venv and installs packages. Later runs: starts straight away.
cd /d "%~dp0"
set "HOST=127.0.0.1"
if /i "%~1"=="lan" (
    set "HOST=0.0.0.0"
    rem Also accept the website when it is opened through this laptop's Wi-Fi address.
    set "CORS_ORIGIN_REGEX=^http://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+):5173$"
)

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
if "%HOST%"=="0.0.0.0" goto lan_banner
echo Backend starting at http://localhost:8000  - API docs: http://localhost:8000/docs
goto run

:lan_banner
echo Backend shared on this Wi-Fi network. Other laptops use this laptop's address:
ipconfig | findstr /c:"IPv4"
echo Website for everyone: http://THAT-ADDRESS:5173   Backend: http://THAT-ADDRESS:8000

:run
echo Press Ctrl+C to stop.
echo.
.venv\Scripts\python -m uvicorn app.main:app --reload --host %HOST%
pause
