# RiftTalk — автоматический Discord‑войс для League of Legends

[English](README.md) | [Russian](README.ru.md)

RiftTalk — opt‑in помощник для войса в LoL. Подключаются только те, кто запустил
клиент; говорить не обязательно (можно просто слушать).

Состоит из двух частей:

- Server: FastAPI + Discord‑бот, создаёт/чистит голосовые каналы и обрабатывает OAuth.
- Client (Windows): WebView‑приложение, читает состояние матча через LCU и
  отправляет события на сервер.

---

## Как это работает (коротко)

1. Клиент читает LCU lockfile и отслеживает фазы матча.
2. На старте матча отправляет событие в API.
3. Сервер создаёт комнаты/роли и разводит участников по командам.
4. На завершении матча всё удаляется.

---

## Структура репозитория

- `client/` - Windows‑клиент (WebView UI + LCU)
- `server/` - FastAPI сервер + Discord‑бот
- `shared/` - общий код и модели
- `rifttalk-site/` - лендинг (опционально)
- `nginx/` - reverse proxy + certbot

---

## Требования

Сервер:

- Python 3.11+ (или Docker)
- Discord‑бот + права в вашем сервере
- Redis (опционально; есть in‑memory fallback)

Клиент:

- Windows 10/11
- League of Legends + запущенный League Client
- Python 3.12/3.13 рекомендуется (pythonnet не поддерживает 3.14)

---

## Переменные окружения (.env)

Используйте `.env.example` как базу. Создайте:

- `server/.env`
- `client/.env`

Должно совпадать на сервере и клиенте:

- `RIFT_SHARED_KEY`

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
PUBLIC_BASE_URL=https://your-domain.com
```

Минимум для клиента (`client/.env`):

```ini
APP_MODE=client
REMOTE_SERVER_URL=https://your-domain.com
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME
SERVER_PORT=8000
```

Опционально:

- `RIFT_MARKETING_DIR` или `RIFT_SITE_DIR` для кастомного пути лендинга.

Примечания:

- `REMOTE_SERVER_URL` указывает на ваш домен (в проде — за Nginx).
- Если Redis недоступен, сервер перейдёт на in‑memory хранилище.

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

Прод (server + redis + nginx + certbot):

```bash
docker compose up -d
```

Локальная сборка сервера:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Подробности — в `DEPLOY_DOCKER.md`.

---

## Health checks

- `GET /api/health` - базовый статус API
- `GET /health` - API + Redis + Discord

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
