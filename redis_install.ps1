# Redis Installation Helper
Write-Host "🗃️ Redis Installation Helper" -ForegroundColor Green
Write-Host "============================" -ForegroundColor Green

Write-Host "`n📥 Download options for Redis:" -ForegroundColor Yellow
Write-Host "1. Redis for Windows (Recommended)" -ForegroundColor White
Write-Host "   Download: https://github.com/microsoftarchive/redis/releases" -ForegroundColor Gray
Write-Host "   Download the latest Redis-x64-3.0.504.msi" -ForegroundColor Gray
Write-Host "`n2. Memurai (Redis-compatible)" -ForegroundColor White
Write-Host "   Download: https://www.memurai.com/" -ForegroundColor Gray
Write-Host "   Free developer edition available" -ForegroundColor Gray

Write-Host "`n3. WSL2 + Redis (Advanced)" -ForegroundColor White
Write-Host "   Requires WSL2 installation" -ForegroundColor Gray

Write-Host "`n💡 After installing Redis, run:" -ForegroundColor Cyan
Write-Host "   redis-server.exe" -ForegroundColor White
Write-Host "   Then check with: redis-cli ping" -ForegroundColor White

Write-Host "`n🎯 Or run this check after installation:" -ForegroundColor Cyan
Write-Host "   .\check-system.ps1" -ForegroundColor White