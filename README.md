# Локальная установка на Windows

## 1. Установка зависимостей
- Python 3.12+
- Redis для Windows

## 2. Настройка
```bash
# Клонируем репозиторий
git clone <repository>
cd lol-voice-chat

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload