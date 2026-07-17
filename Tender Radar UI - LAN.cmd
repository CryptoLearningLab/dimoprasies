@echo off
setlocal
cd /d "%~dp0"
echo Tender Radar UI - LAN mode
echo.
echo This starts the UI on all private network interfaces.
echo Use this only on a trusted LAN or behind Tailscale subnet routing.
echo Keep this window open while using the app.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m tender_radar.ui_server --host 0.0.0.0 --port 8765
) else (
  python -m tender_radar.ui_server --host 0.0.0.0 --port 8765
)
