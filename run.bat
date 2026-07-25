@echo off
REM  Start SARGE and open it in your browser. Leave this window open.
cd /d "%~dp0"
start "" http://127.0.0.1:8383
python app.py
pause
