@echo off
echo ========================================
echo Installing Messenger App
echo ========================================

cd /d "L:\kazem coding\messenger_app"

echo Creating virtual environment...
C:\Users\Seyyed\AppData\Local\Programs\Python\Python311\python.exe -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing packages...
pip install fastapi uvicorn sqlalchemy python-jose[cryptography] passlib[bcrypt] websockets python-multipart

echo Creating directories...
mkdir backend 2>nul
mkdir frontend 2>nul

echo Creating files...
cd backend
type nul > main.py 2>nul
type nul > database.py 2>nul
type nul > models.py 2>nul
type nul > auth.py 2>nul
type nul > websocket_manager.py 2>nul
cd ..

echo ========================================
echo Setup complete!
echo Now copy the code into the files and run:
echo cd backend
echo python main.py
echo ========================================
pause