@echo off
REM ===================================================================
REM  One-time setup. Run this once, then use start.bat every day after.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  Scanned Pages to Excel - Setup
echo  ==============================
echo.

REM --- Python check -------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python was not found.
    echo.
    echo      Install Python 3.12 from python.org, and during the
    echo      installer TICK "Add python.exe to PATH". That tickbox is
    echo      the single most common reason this step fails.
    echo.
    pause
    exit /b 1
)
echo  [ok] Python found.

REM --- Tesseract check ----------------------------------------------
set "TESS=C:\Program Files\Tesseract-OCR\tesseract.exe"
if exist "%TESS%" (
    echo  [ok] Tesseract found.
) else (
    where tesseract >nul 2>&1
    if errorlevel 1 (
        echo  [X] Tesseract OCR was not found.
        echo.
        echo      Download the Windows installer from:
        echo      https://github.com/UB-Mannheim/tesseract/wiki
        echo      Install it to the default location, then run this again.
        echo.
        pause
        exit /b 1
    )
    echo  [ok] Tesseract found on PATH.
)

REM --- Environment --------------------------------------------------
if not exist .venv (
    echo  ... creating environment, this takes a minute
    python -m venv .venv
)
call .venv\Scripts\activate

echo  ... installing components
pip install --quiet --upgrade pip
if exist wheels (
    REM Offline install from the bundled wheels folder - no internet needed.
    REM Check the bundle was built for this Python first: mismatched wheels
    REM fail with "no matching distribution", which sounds like a missing
    REM package rather than a version problem.
    if exist wheels\PYTHON_VERSION.txt (
        set /p BUNDLEVER=<wheels\PYTHON_VERSION.txt
        for /f %%v in ('python -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set LOCALVER=%%v
        if not "!BUNDLEVER!"=="!LOCALVER!" (
            echo  [X] The wheels folder was built for Python !BUNDLEVER!
            echo      but this machine runs Python !LOCALVER!.
            echo      Install Python !BUNDLEVER! here, or rebuild the bundle
            echo      on a machine running Python !LOCALVER!.
            pause
            exit /b 1
        )
    )
    pip install --quiet --no-index --find-links=wheels -r requirements-offline.txt
) else (
    pip install --quiet -r requirements-offline.txt
)
if errorlevel 1 (
    echo  [X] Installation failed. Check your internet connection, or ask
    echo      for the version of this folder that includes a "wheels" folder.
    pause
    exit /b 1
)

if not exist .env (
    echo ENGINE=offline> .env
    if exist "%TESS%" echo TESSERACT_PATH=%TESS%>> .env
    echo MIN_CONFIDENCE=65>> .env
    echo MAX_FILE_MB=50>> .env
)

echo.
echo  Setup complete. Use start.bat from now on.
echo.
pause
