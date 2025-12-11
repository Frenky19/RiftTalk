# LoL Voice Chat Desktop App

## 📋 Project Overview

A Windows desktop application that provides an in‑game voice chat overlay for League of Legends. After the champion-select phase, the app automatically places all players from the same team (who also have the app installed) into a dedicated Discord voice channel where they can communicate during the match. When the game ends, all players are removed from the channel automatically.

## ✨ Features

- ✅ **Automatic creation of Discord voice channels** for teams
- ✅ **In-game overlay** with an intuitive interface
- ✅ **Automatic connection** to the voice channel when the match starts
- ✅ **Automatic disconnection** from the voice channel when the match ends
- ✅ **Account linking** for Discord and League of Legends
- ✅ **Compact interface** without unnecessary elements
- ✅ **Ready-to-run Windows build** (.exe)

## 🛠 Technologies

| Category | Technologies |
|----------|--------------|
| **Backend** | Python, FastAPI, Uvicorn |
| **Frontend** | HTML5, CSS3, JavaScript (ES6+) |
| **Desktop** | PyWebView, PyInstaller |
| **Integrations** | Discord API, League of Legends LCU API |
| **Database** | In-memory storage, Redis (optional) |
| **Authentication** | JWT, Passlib |
| **Validation** | Pydantic |

## 📦 Installation & Build

### Requirements

- **OS:** Windows 10/11 (64-bit)
- **Python:** 3.8 or newer
- **Discord:** Installed and running client
- **League of Legends:** Installed game

### Clone repository

```bash
# Clone repository
git clone <repository-url>
cd GameOverlay-voicechat
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment

1. Copy the example env file to `.env`:

```bash
copy .env.example .env
```

2. Edit the `.env` file with your values.

### Build the application

```bash
# Build EXE
python build.py
```

After a successful build the `dist/` folder will contain:

```
dist/
├── LoLVoiceChat.exe              # Executable
├── LoLVoiceChat/                 # Full application package
│   ├── LoLVoiceChat.exe          # Copy of the EXE
│   ├── Start.bat                 # Launch script
│   └── INFO.txt                  # Application information
└── LoLVoiceChat_v1.0_YYYYMMDD_HHMM.zip  # Distribution ZIP archive
```

## 🚀 Usage

### Running the application

**Option 1: Using the EXE**  
Go to `dist/LoLVoiceChat/` and run `LoLVoiceChat.exe`.

**Option 2: Using the start script**  
Go to `dist/LoLVoiceChat/` and run `Start.bat`.

**Option 3: Development mode**

```bash
# Run development server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Run WebView app
python webview_app.py
```

### How to use

#### Step 1: Prepare Discord

- Make sure Discord is running.
- Join the bot server: https://discord.gg/UcfX74R4
- Enable Developer Mode in Discord:
  Settings → Advanced → Developer Mode → Enable
- Get your Discord ID:
  Right-click your avatar → Copy ID

#### Step 2: Start the app

- Launch League of Legends.
- Start LoL Voice Chat.
- Enter your Discord ID in the input field.
- Click **Link Discord Account**.

#### Step 3: Play

- Join a game (Normal, Ranked, ARAM).
- After the match starts, a connect button will appear in the app.
- Click **Join Voice Channel**.
- Communicate with your team during the match.

#### Step 4: After the match

- You will be automatically disconnected from the channel when the match ends.
- The voice channel will be deleted automatically.

## 📁 Project Structure

```
GameOverlay-voicechat/
├── app/                          # FastAPI main application
│   ├── __init__.py
│   ├── main.py                   # FastAPI entry point
│   ├── config.py                 # Application configuration
│   ├── database.py               # Database access
│   ├── models.py                 # Pydantic data models
│   ├── schemas.py                # Request/response schemas
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   ├── discord_service.py    # Discord integration service
│   │   ├── lol_service.py        # League of Legends service
│   │   └── voice_service.py      # Voice channel management
│   ├── endpoints/                # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py               # Authentication endpoints
│   │   ├── discord.py            # Discord endpoints
│   │   ├── lol.py                # LoL endpoints
│   │   └── voice.py              # Voice endpoints
│   └── middleware/               # Middleware
│       ├── __init__.py
│       └── demo_auth.py          # Demo auth middleware
├── static/                       # Static files
│   ├── logo/                     # Logos and icons
│   │   ├── PNG_LOL.png
│   │   └── icon_L.ico
│   └── link_discord.html         # Main HTML file
├── webview_app.py                # WebView desktop app
├── build.py                      # PyInstaller build script
├── requirements.txt              # Python dependencies
├── .env.example                  # Example env file
├── .env                          # Env file (created)
├── lol_voice_chat.log            # Log file (created)
└── README.md                     # This documentation
```

## 🎨 Interface

### Main interface elements

#### 1. Header and logo
- LoL Voice Chat logo
- Connection status

#### 2. Discord account linking
- Input field for Discord ID (17–20 digits)
- **Link Discord Account** button
- **Change Discord ID** button (if already linked)

#### 3. Match status
- Game state indicator:
  - 🔄 Loading match
  - 🎯 Champion select
  - ⏳ Waiting to start
  - ✅ Match started
- **Refresh status** button

#### 4. Voice channel
- Join link
- **Copy link** button
- Channel information:
  - Channel name
  - Team name
  - Match ID

#### 5. Help panel
- Instructions for obtaining Discord ID
- Link to the Discord server
- Important notes

### UI characteristics

- **Responsive design** — adapts to window size
- **Minimalistic style** — only necessary elements
- **No scrolling** — all content visible at once
- **White background** — clean, professional look
- **Animations** — smooth transitions and loading indicators

## 🔒 Security

### Security measures

1. **Auth tokens** are stored locally only.
2. **Discord ID** is validated before use.
3. **LCU API** is used in read-only mode.
4. **No password storage** — OAuth2 tokens are used.
5. **Local server** — the API runs on localhost only.

### Data protection

- All user data is stored locally by default.
- Discord tokens are not saved in logs.
- No data is sent to external servers.
- Voice channels are removed automatically after the match.

## 🐛 Troubleshooting

### Common issues & solutions:

| Problem | Solution |
|---------|----------|
| **App does not start** | 1. Check the presence of `.env`<br>2. Ensure Python 3.10+ is installed<br>3. Check `lol_voice_chat.log` |
| **Discord account not linking** | 1. Verify the Discord ID<br>2. Ensure you are on the bot server<br>3. Restart Discord |
| **Active match not detected** | 1. Make sure League of Legends is running<br>2. Ensure you are in a game<br>3. Refresh status in the app |
| **No join button available** | 1. Wait for the match to start (after loading)<br>2. Refresh status<br>3. Check logs for errors |
| **Error `uvicorn.protocols.http.auto`** | 1. Rebuild the application: `python build.py`<br>2. Reinstall uvicorn: `pip install uvicorn[standard]` |

### Logging:

- **Main log:** `lol_voice_chat.log` (in the app folder)
- **Log level:** INFO (set DEBUG in `.env` to increase verbosity)
- **Log format:** Time - Module - Level - Message

## 🤝 Development

### How to contribute:

1. **Fork the repository** on GitHub
2. **Create a branch** for your feature:

```bash
git checkout -b feature/amazing-feature
```

3. **Add changes** and commit them:

```bash
git commit -m 'Add amazing feature'
```

4. **Run tests** and make sure everything works:

```bash
pytest tests/
```

5. **Check code style** and documentation:

```bash
black . --check
flake8 .
```

6. **Create a Pull Request** to the main repository:

```bash
git push origin feature/amazing-feature
```

7. **Open the Pull Request** on GitHub

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

```
MIT License

Copyright (c) 2025 LoL Voice Chat Project

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

## 👨‍💻 Author - [Andrey Golovushkin](https://github.com/Frenky19)

Developed to automate team voice communication in **League of Legends**.

**Project goals:**

- **Simplify team communication**
- **Increase win chances** through better coordination
- **Provide a convenient tool** for players
- **Integrate existing platforms** (Discord + LoL)

## 📞 Contact & Support

### Discord server:
- **Invite link:** https://discord.gg/e8ptcwB6c4
- **Channels:** Support, Suggestions, Bug reports

### Reporting bugs:
1. Use **Issues** in the repository
2. Describe the problem in detail:
   - **Steps to reproduce**
   - **Expected behavior**
   - **Actual behavior**
   - **Screenshots/logs**

### Feature requests:
- Create an Issue with the **`enhancement`** tag
- Describe the proposed feature
- Explain how it improves the app

### Questions:
- **Issues:** For technical questions
- **Email:** Best way to get a quick answer