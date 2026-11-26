@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment in %cd%\venv ...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing/verifying dependencies...
pip install -r requirements.txt --quiet

echo Starting PowerMonitorSim server at http://localhost:8010 ...
start "" http://localhost:8010
uvicorn backend.main:app --host 127.0.0.1 --port 8010 --reload

