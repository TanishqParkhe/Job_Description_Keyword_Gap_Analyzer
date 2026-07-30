@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Bhavya AI Resume Analyzer - First-time setup

echo ============================================================
echo  Bhavya AI Resume Analyzer - Team Edition Setup
echo ============================================================
echo This setup creates a local environment and installs dependencies.
echo It is safe to run again; existing packages are reused.
echo.

set "PYTHON_EXE="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=py"
if not defined PYTHON_EXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
  echo Python was not found.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.10 or newer, then run this file again.
    echo Download: https://www.python.org/downloads/windows/
    goto :error
  )
  echo Installing Python 3.12 with Windows Package Manager...
  winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :error
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  ) else (
    echo Python was installed. Close this window and run setup_windows.bat again.
    pause
    exit /b 0
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating the project virtual environment...
  "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 goto :error
) else (
  echo [1/5] Existing virtual environment found - reusing it.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

echo [2/5] Installing required Python packages...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install --upgrade-strategy only-if-needed -r requirements.txt
if errorlevel 1 goto :error

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [3/5] Created local configuration file .env
) else (
  echo [3/5] Existing .env configuration preserved.
)

echo [4/5] Checking OCR support...
where tesseract >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo Tesseract OCR is already installed.
  ) else (
    where winget >nul 2>nul
    if not errorlevel 1 (
      echo Installing Tesseract OCR for scanned resumes and images...
      winget install --id tesseract-ocr.tesseract -e --source winget --accept-package-agreements --accept-source-agreements
      if errorlevel 1 (
        echo The primary Tesseract package was unavailable; trying the alternate package...
        winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
      )
    ) else (
      echo WARNING: Tesseract was not installed. Text PDFs, DOCX and TXT still work.
      echo OCR installer information: https://tesseract-ocr.github.io/tessdoc/Installation.html
    )
  )
) else (
  echo Tesseract OCR is available.
)

echo [5/5] Optional local AI coach...
set "INSTALL_AI=Y"
set /p "INSTALL_AI=Install/configure the local AI coach (about 1.3 GB model download)? [Y/n]: "
if /I "!INSTALL_AI!"=="N" goto :skip_ai

set "OLLAMA_EXE="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"

if not defined OLLAMA_EXE (
  where winget >nul 2>nul
  if not errorlevel 1 (
    echo Installing Ollama...
    winget install --id Ollama.Ollama -e --source winget --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  )
)

if defined OLLAMA_EXE (
  echo Downloading/checking the lightweight llama3.2:1b model...
  "!OLLAMA_EXE!" pull llama3.2:1b
  if errorlevel 1 echo WARNING: The AI model could not be downloaded now. Core analysis still works.
) else (
  echo WARNING: Ollama is unavailable. Core analysis, HR screening and reports still work.
  echo Ollama download: https://ollama.com/download/windows
)

:skip_ai
echo.
echo Running installation verification...
call verify_setup.bat --no-pause

echo.
echo ============================================================
echo Setup complete.
echo Double-click run_app.bat whenever you want to start the app.
echo ============================================================
pause
exit /b 0

:error
echo.
echo SETUP FAILED. Read the message above, fix the issue, and run setup again.
pause
exit /b 1
