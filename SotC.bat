@echo off
rem Shadow of the Colossus PC: settings in sotc.ini (see sotc.py)
cd /d "%~dp0"
python sotc.py %*
if errorlevel 1 pause
