@echo off
cd /d "L:\kazem coding\messenger_app"
call venv\Scripts\activate.bat
cd backend
start "Messenger Server" python main.py
timeout /t 5
start "Tailscale Funnel" tailscale funnel 8000