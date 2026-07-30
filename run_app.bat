@echo off
setlocal
cd /d "%~dp0"
title Bhavya AI Resume Analyzer

if not exist ".venv\Scripts\python.exe" (
  echo The project environment is missing.
  echo Run setup_windows.bat once, then use run_app.bat.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Could not activate the project environment.
  pause
  exit /b 1
)

python -m streamlit run app.py
if errorlevel 1 (
  echo.
  echo The application stopped with an error. Review the message above.
  pause
)
