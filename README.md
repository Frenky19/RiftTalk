# RiftTalk (Discord-integrated team voice)

[English](README.md) | [Russian](README.ru.md)

RiftTalk is split into two parts:

- Server: FastAPI + Discord bot that creates and cleans temporary voice channels.
- Client: Windows desktop app (WebView) that detects match state via LCU and
  calls the server.

> Strict mode: the server must connect to Discord successfully on startup;
> no silent demo fallbacks.

---

## Desktop client

Prebuilt .exe: https://github.com/Frenky19/RiftTalk-Desktop-App

---

## Repo layout

- `client/` - Windows app (WebView UI + LCU integration)
- `server/` - FastAPI server + Discord bot
- `shared/` - shared models/services
- `nginx/` - optional reverse proxy configs

---

## Requirements

Server:
- Python 3.11+ (or Docker)
- Discord bot token and server permissions
- Redis (optional; in-memory fallback is supported)

Client:
- Windows 10/11
- League of Legends + running League Client

---

## Environment variables

Copy `.env.example` into `server/.env` and `client/.env` and edit values.

Minimum for server (`server/.env`):

```ini
APP_MODE=server
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME

DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
DISCORD_GUILD_ID=YOUR_GUILD_ID
DISCORD_OAUTH_CLIENT_ID=YOUR_OAUTH_CLIENT_ID
DISCORD_OAUTH_CLIENT_SECRET=YOUR_OAUTH_CLIENT_SECRET
PUBLIC_BASE_URL=http://your-domain-or-ip:8001
# OR set DISCORD_OAUTH_REDIRECT_URI explicitly
```

Minimum for client (`client/.env`):

```ini
APP_MODE=client
REMOTE_SERVER_URL=http://127.0.0.1:8001
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME
```

Notes:
- `RIFT_SHARED_KEY` must match on server and client.
- If Redis is not reachable, the app falls back to in-memory storage.

---

## Quick start (development)

Server:

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Client:

```bash
cd client
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python webview_app.py
```

---

## Docker (server)

Local run:

```bash
docker compose up --build redis server
```

See `DEPLOY_DOCKER.md` for production deployment details.

---

## Tests

```bash
pip install -r server/requirements.txt -r requirements-dev.txt
pytest
```

---

## Build (Windows client)

```bash
python build.py
```

---

## Security notes

- Never commit `.env` files or bot tokens.
- Use strong secrets for `JWT_SECRET_KEY` and `RIFT_SHARED_KEY`.

---

## License

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
