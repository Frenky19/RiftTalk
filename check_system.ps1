# System Check Script
Write-Host "🔍 LoL Voice Chat - System Check" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green

# Check Python
Write-Host "`n🐍 Python Check:" -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
}

# Check Redis
Write-Host "`n🗃️ Redis Check:" -ForegroundColor Yellow
try {
    $redisCheck = redis-cli ping 2>&1
    if ($redisCheck -eq "PONG") {
        Write-Host "✅ Redis is running" -ForegroundColor Green
    } else {
        Write-Host "❌ Redis not responding" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Redis not installed or not in PATH" -ForegroundColor Red
}

# Check Virtual Environment
Write-Host "`n📁 Virtual Environment Check:" -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✅ Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "❌ Virtual environment not found" -ForegroundColor Red
}

# Check .env file
Write-Host "`n⚙️ Environment Check:" -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✅ .env file exists" -ForegroundColor Green
} else {
    Write-Host "❌ .env file not found" -ForegroundColor Red
}

Write-Host "`n🎉 System check completed!" -ForegroundColor Green