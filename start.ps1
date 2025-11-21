Write-Host "🎮 Starting LoL Voice Chat Application..." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

if (-Not (Test-Path "venv")) {
    Write-Host "❌ Virtual environment not found! Run .\setup.ps1 first" -ForegroundColor Red
    exit 1
}

if (-Not (Test-Path ".env")) {
    Write-Host "❌ .env file not found! Please create .env file" -ForegroundColor Red
    exit 1
}

Write-Host "`n🔧 Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

Write-Host "`n🚀 Starting application..." -ForegroundColor Green
Write-Host "📱 Web interface: http://localhost:8000" -ForegroundColor Cyan
Write-Host "📊 Demo page: http://localhost:8000/demo" -ForegroundColor Cyan
Write-Host "⏹️  Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "`n" + "="*50 -ForegroundColor Green

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload