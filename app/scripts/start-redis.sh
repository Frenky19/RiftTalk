#!/bin/bash

# Скрипт запуска Redis для LoL Voice Chat

set -e

echo "🚀 Starting Redis for LoL Voice Chat..."

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Проверка наличия docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration before running again."
    exit 1
fi

# Загрузка переменных окружения
source .env

# Проверка пароля Redis
if [ "$REDIS_PASSWORD" = "your_secure_password_here" ]; then
    echo "⚠️  Please change REDIS_PASSWORD in .env file for security!"
    exit 1
fi

# Запуск Redis
docker-compose up -d redis

echo "⏳ Waiting for Redis to be ready..."
sleep 5

# Проверка здоровья Redis
if docker-compose exec -T redis redis-cli --raw --no-auth-warning -a "$REDIS_PASSWORD" ping | grep -q "PONG"; then
    echo "✅ Redis is running and responsive!"
    echo "📊 Redis Info:"
    docker-compose exec -T redis redis-cli --raw --no-auth-warning -a "$REDIS_PASSWORD" info memory | grep -E "(used_memory|maxmemory)"
else
    echo "❌ Redis health check failed!"
    docker-compose logs redis
    exit 1
fi

echo "🎉 Redis is ready for LoL Voice Chat!"