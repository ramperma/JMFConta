@echo off
REM Arranca JMFConta usando el venv local (Windows).
cd /d "%~dp0"
set PYTHONPATH=src
.venv\Scripts\python.exe -m jmfconta %*
