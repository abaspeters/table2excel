@echo off
REM ===================================================================
REM  Build the offline install bundle.
REM
REM  Run this ON A MACHINE THAT HAS INTERNET. It downloads every Python
REM  package into a "wheels" folder so the target machine can install
REM  with no connection at all.
REM
REM  You only need this if the machine that will USE the app has no
REM  internet. If it does, skip this and run setup_windows.bat there.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python was not found. Install Python from python.org and
    echo      tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if not exist requirements-offline.txt (
    echo  [X] requirements-offline.txt is not in this folder.
    echo      Make sure this .bat file is sitting inside the project
    echo      folder alongside app.py, and run it from there.
    pause
    exit /b 1
)

REM Detect the Python version rather than hardcoding it. Wheels for
REM compiled packages are tagged to a specific Python version, so 3.12
REM wheels simply will not install under 3.13. Getting this wrong gives
REM you a bundle that fails on the offline machine, which is the worst
REM possible place to discover it.
for /f "tokens=1,2 delims=." %%a in ('python -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)
set PYVER=!PYMAJOR!.!PYMINOR!

echo.
echo  Building bundle for Python !PYVER! on 64-bit Windows.
echo.
echo  IMPORTANT: the offline machine must run Python !PYVER! too.
echo  If it will run a different version, install that version here
echo  first and re-run this script.
echo.
pause

if exist wheels rmdir /s /q wheels
mkdir wheels

echo  Downloading... this needs internet and takes a few minutes.
echo.

REM --platform and --python-version force WINDOWS packages specifically.
REM Without them pip grabs packages for whatever machine you are on.
python -m pip download -r requirements-offline.txt -d wheels ^
    --platform win_amd64 --python-version !PYVER! --only-binary=:all:

if errorlevel 1 (
    echo.
    echo  [X] Download failed. Check your internet connection.
    pause
    exit /b 1
)

echo !PYVER!> wheels\PYTHON_VERSION.txt

echo.
echo  Done. The "wheels" folder now holds the packages.
echo.
echo  Next:
echo    1. Copy this WHOLE folder (including wheels) to a USB drive.
echo    2. Also copy the Python !PYVER! installer and the Tesseract installer.
echo    3. On the offline machine: install those two, then run
echo       setup_windows.bat. It finds the wheels folder automatically.
echo.
pause
