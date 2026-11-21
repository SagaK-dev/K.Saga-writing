@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo [ERROR] First run install-windows.ps1 using PowerShell.
 pause
 exit /b 1
)
set "HWF_DATA_DIR=%USERPROFILE%\.handwritefont"
start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn hwf.api:app --app-dir backend --host 127.0.0.1 --port 8765
pause
