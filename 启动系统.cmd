@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON="
if exist ".venv\Scripts\python.exe" set "APP_PYTHON=%CD%\.venv\Scripts\python.exe"
if not defined APP_PYTHON if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "APP_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined APP_PYTHON set "APP_PYTHON=python"

"%APP_PYTHON%" -c "import openpyxl" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is missing openpyxl.
  echo Run: python -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo Starting local service at http://127.0.0.1:8000 ...
start "Trade Query Service" "%APP_PYTHON%" run.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000"
endlocal
