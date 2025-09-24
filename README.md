# Redis Configuration (без пароля для теста)
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=

# Остальные настройки...
# Останавливаем текущий Redis
docker-compose down

# Запускаем Redis без пароля
docker run -d -p 6379:6379 --name redis-test redis:7.2-alpine
uvicorn app.main:sio_app --reload