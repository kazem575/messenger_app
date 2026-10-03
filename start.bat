@echo off
title Messenger App Launcher
color 0A

echo ========================================
echo   Messenger App - Starting...
echo ========================================
echo.

cd /d "C:\Users\Seyyed\Desktop\messenger_app"
call venv\Scripts\activate.bat

echo [1/2] Starting FastAPI Server...
cd backend
start "Messenger Server" cmd /k python main.py

echo Waiting 5 seconds...
timeout /t 5 /nobreak >nul

echo [2/2] Starting Tailscale Funnel...
cd /d "C:\Users\Seyyed\Desktop\messenger_app"
start "Tailscale Funnel" cmd /k tailscale funnel 8000

echo.
echo ========================================
echo   All services started!
echo   URL: https://desktop-1ebo8os.taile7482d.ts.net/static
echo ========================================
echo.
echo Press any key to close this launcher...
pause >nul