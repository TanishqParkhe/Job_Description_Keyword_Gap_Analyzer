@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] Virtual environment not found. Run setup_windows.bat.
  if /I not "%~1"=="--no-pause" pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python verify_setup.py
set "STATUS=%ERRORLEVEL%"
if /I not "%~1"=="--no-pause" pause
exit /b %STATUS%
