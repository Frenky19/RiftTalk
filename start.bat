@echo off
chcp 65001 >nul
echo.
echo 🎮 Starting LoL Voice Chat Application...
echo ==========================================

if not exist "venv\" (
    echo ❌ Virtual environment not found!
    echo 💡 Run setup.ps1 first
    pause
    exit /b 1
)

if not exist ".env" (
    echo ❌ .env file not found!
    echo 💡 Create .env file with your configuration
    pause
    exit /b 1
)

echo.
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo 🚀 Starting application...
echo 📱 Web interface: http://localhost:8000
echo 📊 Demo page: http://localhost:8000/demo
echo ⏹️  Press Ctrl+C to stop
echo.
echo ==========================================
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause