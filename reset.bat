@echo off
echo Stopping server...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo Deleting database...
cd /d "L:\kazem coding\messenger_app\backend"
if exist messenger.db (
    del messenger.db
    echo Database deleted!
) else (
    echo Database not found!
)

echo Starting server...
cd /d "L:\kazem coding\messenger_app"
call venv\Scripts\activate.bat
cd backend
start "Messenger Server" python main.py

echo Done!
pause