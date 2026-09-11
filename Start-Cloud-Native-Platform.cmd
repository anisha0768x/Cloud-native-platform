@echo off
setlocal
cd /d "%~dp0"
if exist "CloudNativePlatform\.venv\Scripts\python.exe" (
  "CloudNativePlatform\.venv\Scripts\python.exe" launch_platform.py
) else (
  ".venv\Scripts\python.exe" launch_platform.py
)
if errorlevel 1 pause
endlocal
