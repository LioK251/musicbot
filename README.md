# 🎵 Full-Featured Discord Music Bot + TikTok Auto-Embed

A modular, high-performance next-generation Discord bot built with **Python 3.10+** and **discord.py 2.x**, featuring slash commands, interactive Discord UI components (buttons, dropdown select menus), multi-threaded asynchronous audio streaming, and automatic TikTok video embedding.

---

## 🌟 Key Features

### 1. 🎶 Music Playback System (/play)
- **Audio Sources:**
  - **YouTube:** Videos, live streams, and playlists (with instant playback of the first track and lazy-loading for subsequent items).
  - **SoundCloud:** Individual tracks and sets.
  - **Spotify:** Integration via Spotify Web API (`spotipy`). Supports single tracks, albums, and playlists (metadata is extracted and streamed in high quality via YouTube/SoundCloud). If API keys are not provided, an integrated **oEmbed Fallback** resolves single tracks seamlessly.
- **Live Autocomplete (Discord Slash Command Autocomplete):**
  - Typing a song title in `/play query:` instantly displays a dynamic top-5 list of matching tracks with titles and durations in real-time.
- **Instant Playback and Search:**
  - Sending `/play <query>` selects the top match (#1) and starts playing immediately with no extra clicks.
  - The `/search <query>` command displays an interactive **Select Menu** with top-5 results, showing author, duration, and a **Cancel** button.
- **Smart Queue System:**
  - FIFO queue with multiple loop modes:
    - ➡️ `Off` (standard sequential playback)
    - 🔂 `Track` (repeats current track; manual skip moves to the next track)
    - 🔁 `Queue` (re-queues track at the end when finished)
  - Queue shuffling (`/shuffle`), track removal (`/remove <index>`), and paginated queue listing (`/queue`).
- **Voice Controller:**
  - Automatic disconnection after inactivity (**Idle Timeout**, default 5 minutes).
  - Automatic disconnection after 30 seconds if all users leave the voice channel (**Empty Channel Auto-Leave**).
  - Server-side bot deafening (`self_deaf=True`) to minimize network bandwidth.

### 2. 🎛️ Interactive Player (Discord UI ActionRow)
When a track starts playing, the bot sends an embed containing track title, URL, uploader, requester, and a **dynamic progress bar** (`🔘▬▬▬▬▬▬▬▬ 01:23 / 03:45`).

Attached directly below the embed is a row of interactive controls:
- ⏯️ **Pause / Resume** — Toggles playback state, updating button styling and embed status.
- ⏭️ **Skip** — Skips current track without skipping subsequent songs.
- 🔁 **Loop** — Cycles loop modes: Off ➡️ 🔂 Track ➡️ 🔁 Queue.
- ⏹️ **Stop** — Clears the queue, stops playback, and disconnects the bot from voice.
- 🛡️ **Voice Verification:** Only members in the bot's current voice channel can interact with the controls.

### 3. 📱 TikTok Integration
- An `on_message` listener intercepts all variants of TikTok links:
  - `tiktok.com/@username/video/12345`
  - `vm.tiktok.com/ZMxxxx/`
  - `vt.tiktok.com/ZSxxxx/`
  - `tiktok.com/t/ZTxxxx/`
- Downloads and uploads the native video directly into chat, or replaces the link with an embeddable mirror (`vxtiktok.com`).
- Configurable settings via `.env`:
  - `TIKTOK_SEND_VIDEO=true`: Downloads and sends video file up to 25MB.
  - `TIKTOK_DELETE_ORIGINAL=true`: Deletes original message to prevent duplicates.
  - Manual command `/tiktok <url>` for on-demand video downloads.

---

## 📁 Project Structure

```
musicbot/
│
├── .env.example              # Sample environment variables with documentation
├── .env                      # Active local configuration (git-ignored)
├── .gitignore                # Git ignore rules (env, venv, logs, cache)
├── requirements.txt          # Python dependencies
├── run.bat                   # Windows one-click startup script
├── start.bat                 # Short launch alias
├── README.md                 # Project documentation
├── bot.py                    # Main entry point (bot initialization, Cogs loader, error handler)
├── config.py                 # Configuration validation and environment loader
│
├── core/                     # Core system
│   ├── __init__.py
│   ├── logger.py             # ANSI color console logger and rotating file log (bot.log)
│   ├── errors.py             # Custom exceptions and centralized App Command Error Handler
│   └── checks.py             # Voice state, permissions, and channel matching checks
│
├── music/                    # Music subsystem
│   ├── __init__.py
│   ├── source.py             # YTDLSource, Track dataclass, FFmpeg audio streams, search
│   ├── spotify.py            # Spotify Web API client + oEmbed fallback
│   ├── queue.py              # FIFO music queue, loop modes, shuffle
│   ├── player.py             # Guild-level MusicPlayer controller, progress bar, idle timer
│   └── views.py              # Discord UI: select dropdown, player buttons, queue pagination
│
├── cogs/                     # Bot extensions (Cogs)
│   ├── __init__.py
│   ├── music.py              # Slash commands (/play, /pause, /skip, /queue, /volume, etc.)
│   ├── tiktok.py             # TikTok message listener and /tiktok slash command
│   └── general.py            # General utility commands (/help, /ping, /info)
│
├── tests/                    # Unit and integration test suite
│   ├── test_components.py    # Queue, loop modes, TikTok & Spotify regex tests
│   ├── test_player_flow.py   # Playback lifecycle, skip logic, playlist handling
│   ├── test_autocomplete_and_search.py # Autocomplete and top-5 search tests
│   ├── test_live_search.py   # Live yt-dlp search test
│   ├── test_live_track_stream.py # Audio stream extraction & FFmpeg test
│   └── test_spotify_oembed.py # Spotify oEmbed metadata extraction test
│
└── logs/                     # Automatically created log directory
    └── bot.log
```

---

## ⚙️ System Dependencies

Playing audio in Discord voice channels requires two system dependencies: **FFmpeg** and **Opus**.

### 1. Installing FFmpeg

#### 🪟 Windows:
Method 1 (via Windows Terminal / winget):
```powershell
winget install Gyan.FFmpeg
```
or via Scoop:
```powershell
scoop install ffmpeg
```
or via Chocolatey:
```powershell
choco install ffmpeg
```

Method 2 (Manual):
1. Download `ffmpeg-release-full.7z` from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/).
2. Extract the archive into `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your system `PATH` environment variable.
4. Open a new terminal and verify:
   ```powershell
   ffmpeg -version
   ```

#### 🐧 Linux (Ubuntu / Debian / Raspberry Pi OS):
```bash
sudo apt update
sudo apt install -y ffmpeg libopus-dev
```

#### 🐧 Linux (Arch / Manjaro):
```bash
sudo pacman -S ffmpeg opus
```

#### 🍎 macOS:
```bash
brew install ffmpeg opus
```

---

### 2. Opus Library (PyNaCl)
- In `discord.py 2.x`, voice encoding is powered by **PyNaCl**.
- It is included in `requirements.txt` (`PyNaCl>=1.5.0`) and provides bundled Opus binaries for Windows, Linux, and macOS. No separate DLL installation is needed on Windows.

---

## 🚀 Setup & Launch

### Step 1. Create a Bot in Discord Developer Portal
1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **"New Application"**, enter a name for the bot, and confirm.
3. Open the **"Bot"** tab:
   - Click **"Reset Token"** and copy the bot token (needed for `.env`).
   - Under **"Privileged Gateway Intents"**, enable:
     - ✅ **Message Content Intent** (required for TikTok auto-detection in chat).
     - ✅ **Server Members Intent** (recommended for tracking member voice states).
4. Open the **"OAuth2" -> "URL Generator"** tab:
   - Under **Scopes**, select: `bot`, `applications.commands`.
   - Under **Bot Permissions**, select:
     - `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Manage Messages` (for TikTok module).
     - `Connect`, `Speak`, `Use Voice Activity` (for Music player).
   - Copy the generated invite link at the bottom and authorize the bot on your server.

---

### Step 2. (Optional) Configure Spotify Web API
For loading full Spotify playlists and albums (single tracks work without this step via oEmbed):
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Log in and click **"Create App"**.
3. Name your application and specify `http://localhost` as the Redirect URI.
4. In the app settings, copy:
   - **Client ID**
   - **Client Secret**

---

### Step 3. Installation and Running

1. Clone or navigate to the project directory:
   ```bash
   cd c:/Script/musicbot
   ```

2. Create a Python virtual environment (Python 3.10+ recommended):
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - **Windows (PowerShell):**
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure `.env`:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and set your `DISCORD_TOKEN`, along with optional Spotify credentials and guild ID.

6. Launch the bot:
   - On Windows: double-click `run.bat` or run:
     ```powershell
     .\venv\Scripts\python.exe bot.py
     ```
   - On Linux / macOS:
     ```bash
     python bot.py
     ```

---

## 📋 Slash Commands Reference

| Slash Command | Description |
| :--- | :--- |
| `/play <query>` | Play audio (YouTube, SoundCloud, Spotify) with real-time autocomplete |
| `/search <query>` | Interactive search for top 5 YouTube tracks with a dropdown selection menu |
| `/pause` | Pause current playback |
| `/resume` | Resume paused playback |
| `/skip` | Skip current track |
| `/stop` | Stop playback, clear queue, and disconnect from voice channel |
| `/queue` | Display current playback queue with pagination |
| `/nowplaying` | Show currently playing track card with dynamic progress bar and interactive controls |
| `/loop [off\|track\|queue]` | Change loop mode |
| `/shuffle` | Shuffle tracks in the queue |
| `/volume <0-100>` | Adjust playback volume |
| `/remove <index>` | Remove a track from the queue by position |
| `/tiktok <url>` | Download and send a TikTok video directly to chat |
| `/ping` | Display WebSocket latency and REST API roundtrip time |
| `/help` | Detailed guide and command reference |
| `/info` | Technical information, system environment, and uptime |

---

## 🧪 Running Automated Tests

Run the full automated test suite with:
```powershell
.\venv\Scripts\python.exe -m unittest discover tests
```
The test suite validates queue operations, loop transitions, single-skip behavior, playlist handling, TikTok and Spotify regex patterns, oEmbed extraction, and live audio stream initialization.
