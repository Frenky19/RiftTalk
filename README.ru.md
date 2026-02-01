# RiftTalk (командный голосовой чат через Discord)

[English](README.md) | [Русский](README.ru.md)

RiftTalk состоит из двух частей:

- Server: FastAPI + Discord-бот, который создает и удаляет временные голосовые каналы.
- Client: Windows-приложение (WebView), которое отслеживает матч через LCU и
  отправляет события на сервер.

> Strict mode: сервер обязан успешно подключиться к Discord при старте;
> никаких скрытых демо-режимов.

---

## Десктопный клиент

Готовый .exe: https://github.com/Frenky19/RiftTalk-Desktop-App

---

## Структура репозитория

- `client/` - Windows-приложение (WebView UI + LCU)
- `server/` - FastAPI сервер + Discord-бот
- `shared/` - общий код и модели
- `nginx/` - опциональные конфиги reverse proxy

---

## Требования

Сервер:
- Python 3.11+ (или Docker)
- Discord-бот и права на управление каналами/ролями
- Redis (опционально; есть in-memory fallback)

Клиент:
- Windows 10/11
- Установленная League of Legends и запущенный League Client

---

## Переменные окружения

Скопируйте `.env.example` в `server/.env` и `client/.env` и отредактируйте.

Минимум для сервера (`server/.env`):

```ini
APP_MODE=server
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME

DISCORD_BOT_TOKEN=ВАШ_ТОКЕН_БОТА
DISCORD_GUILD_ID=ID_СЕРВЕРА
DISCORD_OAUTH_CLIENT_ID=OAUTH_CLIENT_ID
DISCORD_OAUTH_CLIENT_SECRET=OAUTH_CLIENT_SECRET
PUBLIC_BASE_URL=http://ваш-домен-или-ip:8001
# либо укажите DISCORD_OAUTH_REDIRECT_URI
```

Минимум для клиента (`client/.env`):

```ini
APP_MODE=client
REMOTE_SERVER_URL=http://127.0.0.1:8001
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME
```

Примечания:
- `RIFT_SHARED_KEY` должен совпадать на сервере и на клиенте.
- Если Redis недоступен, приложение перейдет на in-memory хранилище.

---

## Быстрый старт (разработка)

Сервер:

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Клиент:

```bash
cd client
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python webview_app.py
```

---

## Docker (сервер)

Локальный запуск:

```bash
docker compose up --build redis server
```

Подробности — в `DEPLOY_DOCKER.md`.

---

## Тесты

```bash
pip install -r server/requirements.txt -r requirements-dev.txt
pytest
```

---

## Сборка (Windows клиент)

```bash
python build.py
```

---

## Безопасность

- Никогда не коммитьте `.env` и токены.
- Используйте сильные секреты для `JWT_SECRET_KEY` и `RIFT_SHARED_KEY`.

---

## Лицензия

```
MIT License

Copyright (c) 2026 Frenky19

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
