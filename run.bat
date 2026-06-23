@echo off
REM SpookFi — Windows Launch Script
REM Starts both the FastAPI engine (on port 8000) and Streamlit dashboard (on port 8501)

setlocal

echo.
echo  ==========================================
echo   ^👻 SpookFi — Autonomous Trading Engine
echo  ==========================================
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    exit /b 1
)

REM Create venv if missing
if not exist "venv\" (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install / upgrade dependencies
echo [SETUP] Installing dependencies...
pip install -q -r requirements.txt

REM Create logs directory
if not exist "logs\" mkdir logs

echo.
echo [INFO] Starting SpookFi FastAPI Engine on http://localhost:8000 ...
start "SpookFi API" cmd /k "venv\Scripts\activate && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [INFO] Starting Streamlit Dashboard on http://localhost:8501 ...
start "SpookFi Dashboard" cmd /k "venv\Scripts\activate && streamlit run dashboard/app.py --server.port 8501"

echo.
echo  ==========================================
echo   SpookFi is running!
echo   UI:        http://localhost:8000
echo   Dashboard: http://localhost:8501
echo  ==========================================
echo.
echo  Press Ctrl+C in each terminal window to stop.
