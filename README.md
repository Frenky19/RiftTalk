# Локальная установка на Windows

## 1. Установка зависимостей
- Python 3.12+
- Redis для Windows

## 2. Настройка
```bash
# Клонируем репозиторий
git clone <repository>
cd lol-voice-chat

# Устанавливаем
.\setup.ps1

# Запускаем Redis (отдельное окно)
redis-server.exe

# Запускаем приложение (другое окно)
.\start.ps1