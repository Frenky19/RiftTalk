# RiftTalk — automatic Discord voice for League of Legends

[English](README.md) | [Russian](README.ru.md)

RiftTalk is an opt-in Discord voice helper for LoL. Only players who run the
client are connected; speaking is optional (listen-only works).

It consists of:

- Server: FastAPI + Discord bot that creates/cleans voice channels and handles OAuth.
- Client (Windows): WebView app that reads LCU state and calls the server.

---

## How it works (short)

1. Client reads the LCU lockfile and tracks match phases.
2. On match start it posts to the server API.
3. Server creates rooms/roles and moves connected users into their team channels.
4. On match end it cleans everything up.

---

## Repo layout

- `client/` - Windows client (WebView UI + LCU integration)
- `server/` - FastAPI server + Discord bot
- `shared/` - shared models/services
- `rifttalk-site/` - marketing site (optional)
- `nginx/` - reverse proxy + certbot configs

---

## Requirements

Server:

- Python 3.11+ (or Docker)
- Discord bot token + permissions in your guild
- Redis (optional; in-memory fallback exists)

Client:

- Windows 10/11
- League of Legends + running League Client
- Python 3.12/3.13 recommended (pythonnet does not support 3.14)

---

## Configuration (.env)

Use `.env.example` as a starting point. Create:

- `server/.env`
- `client/.env`

Must match on both server and client:

- `RIFT_SHARED_KEY`

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
PUBLIC_BASE_URL=https://your-domain.com
```

Minimum for client (`client/.env`):

```ini
APP_MODE=client
REMOTE_SERVER_URL=https://your-domain.com
RIFT_SHARED_KEY=CHANGE_ME
JWT_SECRET_KEY=CHANGE_ME
SERVER_PORT=8000
```

Optional:

- `RIFT_MARKETING_DIR` or `RIFT_SITE_DIR` to serve the marketing site from a custom path.

Notes:

- `REMOTE_SERVER_URL` should point to your server domain (behind Nginx in prod).
- If Redis is not reachable, the server falls back to in-memory storage.

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

Production (server + redis + nginx + certbot):

```bash
docker compose up -d
```

Local dev (build server image locally):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

See `DEPLOY_DOCKER.md` for VPS + HTTPS setup.

---

## Health checks

- `GET /api/health` - basic API health
- `GET /health` - API + Redis + Discord status

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
