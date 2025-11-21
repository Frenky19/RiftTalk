# LoL Voice Chat - Setup Script for Windows
Write-Host "🎮 LoL Voice Chat - Windows Setup" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green

# Проверяем Python
Write-Host "`n🔍 Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found! Please install Python 3.8+ from https://python.org" -ForegroundColor Red
    exit 1
}

# Проверяем pip
Write-Host "`n🔍 Checking pip..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version
    Write-Host "✅ pip is available" -ForegroundColor Green
} catch {
    Write-Host "❌ pip not found!" -ForegroundColor Red
    exit 1
}

# Создаем виртуальное окружение
Write-Host "`n🐍 Creating virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "🔄 Virtual environment already exists. Recreating..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "venv"
}

python -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create virtual environment" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Virtual environment created" -ForegroundColor Green

# Активируем venv
Write-Host "`n🔧 Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Обновляем pip
Write-Host "`n🔄 Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Устанавливаем зависимости
Write-Host "`n📦 Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Dependencies installed successfully" -ForegroundColor Green

# Проверяем .env файл
if (Test-Path ".env") {
    Write-Host "✅ Using existing .env file" -ForegroundColor Green
} else {
    Write-Host "⚠️  .env file not found - please create it" -ForegroundColor Yellow
}

Write-Host "`n🎉 Setup completed successfully!" -ForegroundColor Green
Write-Host "`n📝 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Ensure Redis is running on localhost:6379" -ForegroundColor White
Write-Host "   2. Run .\start.ps1 to start the application" -ForegroundColor White
Write-Host "   3. Open http://localhost:8000/demo" -ForegroundColor White