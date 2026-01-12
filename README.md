# LoL Voice Chat Desktop (Discord-integrated team voice)

[English](README.md) | [Русский](README.ru.md)

A Windows desktop app that automatically connects League of Legends teammates (who also run the app) into temporary Discord voice channels **at match start**, and cleans everything up **after the match**.

> **Strict mode**: the app requires a working Discord bot connection at startup (no demo/mock fallbacks).

---

## What it does

- Detects match lifecycle via **League Client (LCU)** on Windows.
- At match start:
  - Creates a temporary **team voice channel** (Blue/Red).
  - Grants access via roles/permissions.
  - Moves/joins linked users into their team channel.
- After match ends:
  - Removes roles / kicks users from the temp channel.
  - Deletes temporary channels.
- Includes an embedded WebView UI.

---

## Requirements

- **Windows 10/11**
- **Python 3.11+** (recommended) or a built build (see Build)
- **Discord server** where you have permission to add a bot and manage channels/roles
- League of Legends installed and the **League Client running**

---

## Quick start (development)

1) Create venv and install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Create `.env` in the project root (see Environment variables below)

3) Run

```bash
python webview_app.py
```

---

## Environment variables

Create a `.env` file in the project root:

```ini
# Required (strict mode)
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
DISCORD_GUILD_ID=YOUR_SERVER_ID

# Optional (recommended)
DISCORD_CATEGORY_ID=VOICE_CATEGORY_ID            # where to create temp channels
DISCORD_OAUTH_CLIENT_ID=YOUR_OAUTH_CLIENT_ID     # if you use Discord account linking
DISCORD_OAUTH_CLIENT_SECRET=YOUR_OAUTH_SECRET
DISCORD_OAUTH_REDIRECT_URI=http://127.0.0.1:PORT/discord/callback

# App behavior
DEBUG=false
REDIS_URL=memory://                              # default: in-memory storage
```

Notes:
- If `REDIS_URL` is not set or Redis is unavailable, the app can use in-memory storage.
- If Discord required variables are missing or the bot cannot connect, the app **won’t start**.

---

## Discord bot setup

1) Create an app in Discord Developer Portal, add a **Bot**.
2) Enable **Privileged Gateway Intents** if your implementation needs them:
   - *Server Members Intent* (often required to fetch/move members reliably)
3) Grant permissions:
   - Manage Channels
   - Manage Roles
   - Move Members
   - View Channels
   - Connect / Speak
4) Invite the bot to your server.

Make sure your bot role is **above** any roles it needs to assign/manage.

---


## Build

This repository includes scripts for building a distributable Windows app (exact build steps depend on your chosen toolchain, e.g. PyInstaller).

Typical workflow:

```bash
python build.py
```

If you change build tooling, keep **strict mode** behavior: no silent fallbacks when Discord is not available.

---

## Troubleshooting

### App fails on startup: “Discord connection failed”
- Check `DISCORD_BOT_TOKEN` and `DISCORD_GUILD_ID`
- Ensure the bot is added to the server and online
- Verify category/channel permissions and role hierarchy

### LCU not detected
- Start League Client and ensure the `lockfile` exists
- Run the app with normal user permissions (or match the permissions level of the League Client)

---

## Security notes

- Keep `.env` private (never commit bot tokens).
- Prefer `127.0.0.1` redirect URIs for local OAuth flows.

---

## Contributing

PRs are welcome:
- Bug fixes and cleanup improvements
- Better logging and diagnostics
- UI/UX improvements for the WebView

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
