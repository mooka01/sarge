@echo off
REM ============================================================
REM  SARGE one-command setup - no software knowledge required.
REM  Double-click this file. It checks Python, installs what's
REM  needed, downloads the manual index, and starts SARGE.
REM ============================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python is not installed. Opening the Microsoft Store page...
    echo  Install "Python 3.12" or newer, then run this file again.
    start ms-windows-store://pdp/?ProductId=9NCVDN91XZQP
    pause
    exit /b 1
)

echo Installing components (one-time, a few minutes)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Something went wrong installing components. Screenshot this window
    echo and ask for help on the SARGE GitHub page.
    pause
    exit /b 1
)

python setup_wizard.py
pause
