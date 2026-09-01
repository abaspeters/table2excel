@echo off
cd /d "%~dp0"
if not exist .venv (
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate
echo Starting... your browser will open shortly. Keep this window open.
streamlit run app.py
pause
