# Shelfmark Telegram Bot

A Telegram bot for searching and downloading books via your [Shelfmark](https://github.com/calibrain/shelfmark) instance.

## Features

- **Search** books by title, author, or keyword
- **Browse** detailed book information
- **Find releases** from multiple sources (Direct Download, Prowlarr)
- **Filter** releases by source
- **Download** with one-tap confirmation
- **Monitor** download queue status

## Quick Start

### 1. Create a Telegram Bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram and create a new bot. Copy the token.

### 2. Configure

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token from BotFather |
| `SHELFMARK_URL` | Yes | URL of your Shelfmark instance (e.g. `http://192.168.0.232:8084`) |
| `ALLOWED_USER_IDS` | No | Comma-separated Telegram user IDs to restrict access |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

### 3. Run

#### With Docker (recommended)

```bash
docker compose up -d --build
```

#### Without Docker

```bash
pip install -r requirements.txt
python -m bot.main
```

## Usage

| Command | Description |
| --- | --- |
| `/search <query>` | Search for a book |
| `/s <query>` | Short alias for search |
| `/status` | Check download queue |
| `/help` | Show help |

You can also just send a text message with a book title — the bot will search for it automatically.

### Workflow

1. Send a search query (e.g. `/search Dune`)
2. Tap a book from the results
3. Tap **Find Releases** to see available downloads
4. Use filter buttons to switch between **Direct Download** and **Prowlarr** sources
5. Tap a release to download
6. Confirm the download
7. Use `/status` to monitor progress

## Architecture

```text
bot/
├── main.py              # Entry point, handler registration
├── config.py            # Environment variable configuration
├── shelfmark_client.py  # Async HTTP client for Shelfmark API
├── utils.py             # Formatting, keyboards, access control
└── handlers/
    ├── search.py        # /search command + plain text search
    ├── book.py          # Book detail view
    ├── releases.py      # Release listing, filtering, download
    └── status.py        # /status command
```

## License

MIT
