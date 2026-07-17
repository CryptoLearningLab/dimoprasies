@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m tender_radar.ui_server --open
) else (
  python -m tender_radar.ui_server --open
)
